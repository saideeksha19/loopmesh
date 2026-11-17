"""Proposal and transaction workflow engine.

All lifecycle writes funnel through :class:`WorkflowService`. It is the only
place that:

* resolves a rule from :mod:`app.services.lifecycle` and rejects impossible
  transitions with a 409,
* checks the actor's role, organisation scope and segregation of duties,
* enforces optimistic concurrency (:attr:`version`),
* writes the append-only transition row *and* the audit event inside the same
  database transaction as the state change.

No endpoint, script or agent may assign ``status`` directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.actors import ActorContext
from app.core.exceptions import (
    ConflictError,
    EvidenceRequiredError,
    ForbiddenError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
)
from app.db.enums import (
    ActorRole,
    CompatibilityStatus,
    ProposalStatus,
    TransactionStatus,
    TransitionEntity,
    VerificationMethod,
)
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.db.models.transition import StatusTransition
from app.services import audit, lifecycle
from app.services.lifecycle import Party, TransitionRule

# Fields each action stamps with the acting identity.
_ACTOR_FIELDS: dict[tuple[str, str], str] = {
    ("proposal", "submit"): "submitted_by",
    ("proposal", "review"): "reviewed_by",
    ("proposal", "approve"): "approved_by",
    ("proposal", "reject"): "rejected_by",
    ("proposal", "withdraw"): "withdrawn_by",
    ("transaction", "reject"): "rejected_by",
    ("transaction", "cancel"): "cancelled_by",
}

_REASON_FIELDS: dict[tuple[str, str], str] = {
    ("proposal", "reject"): "rejection_reason",
    ("proposal", "cancel"): "cancellation_reason",
    ("proposal", "fail"): "failure_reason",
    ("transaction", "reject"): "rejection_reason",
    ("transaction", "cancel"): "cancellation_reason",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    cleaned = reason.strip()
    return cleaned or None


class WorkflowService:
    """Lifecycle operations scoped to one actor and one database session."""

    def __init__(self, session: Session, actor: ActorContext) -> None:
        self.session = session
        self.actor = actor

    # ------------------------------------------------------------------
    # loading and scoping
    # ------------------------------------------------------------------
    def scope_proposals(self, statement: Select, *, organization_id: uuid.UUID | None = None) -> Select:
        """Restrict a proposal query to what this actor may read."""
        if organization_id is not None:
            if not self.actor.sees_all_records and organization_id not in self.actor.organization_ids:
                raise ForbiddenError(
                    "You cannot filter proposals by another organisation.",
                    details={"reason": "organisation_scope"},
                )
            return statement.where(
                (RecoveryProposal.proposed_by_organization_id == organization_id)
                | (RecoveryProposal.receiving_organization_id == organization_id)
            )
        if self.actor.sees_all_records:
            return statement
        org_ids = set(self.actor.organization_ids)
        if not org_ids:
            return statement.where(RecoveryProposal.id.is_(None))
        return statement.where(
            (RecoveryProposal.proposed_by_organization_id.in_(org_ids))
            | (RecoveryProposal.receiving_organization_id.in_(org_ids))
        )

    def scope_transactions(
        self, statement: Select, *, organization_id: uuid.UUID | None = None
    ) -> Select:
        if organization_id is not None:
            if not self.actor.sees_all_records and organization_id not in self.actor.organization_ids:
                raise ForbiddenError(
                    "You cannot filter transactions by another organisation.",
                    details={"reason": "organisation_scope"},
                )
            return statement.where(
                (RecoveryTransaction.source_organization_id == organization_id)
                | (RecoveryTransaction.destination_organization_id == organization_id)
            )
        if self.actor.sees_all_records:
            return statement
        org_ids = set(self.actor.organization_ids)
        if not org_ids:
            return statement.where(RecoveryTransaction.id.is_(None))
        return statement.where(
            (RecoveryTransaction.source_organization_id.in_(org_ids))
            | (RecoveryTransaction.destination_organization_id.in_(org_ids))
        )

    def get_proposal(self, proposal_id: uuid.UUID, *, lock: bool = False) -> RecoveryProposal:
        proposal = self.session.get(RecoveryProposal, proposal_id, with_for_update=lock)
        if proposal is None:
            raise NotFoundError("Proposal not found.")
        self._ensure_visible(
            {proposal.proposed_by_organization_id, proposal.receiving_organization_id}
        )
        return proposal

    def get_transaction(
        self, transaction_id: uuid.UUID, *, lock: bool = False
    ) -> RecoveryTransaction:
        transaction = self.session.get(RecoveryTransaction, transaction_id, with_for_update=lock)
        if transaction is None:
            raise NotFoundError("Transaction not found.")
        self._ensure_visible(
            {transaction.source_organization_id, transaction.destination_organization_id}
        )
        return transaction

    def _ensure_visible(self, organization_ids: set[uuid.UUID]) -> None:
        """Cross-organisation reads are reported as 404, never as 403.

        404 avoids confirming that a record exists to an unrelated party.
        """
        if self.actor.sees_all_records:
            return
        if not (set(self.actor.organization_ids) & organization_ids):
            raise NotFoundError("Record not found.")

    # ------------------------------------------------------------------
    # proposal creation
    # ------------------------------------------------------------------
    def create_proposal(
        self,
        *,
        opportunity_id: uuid.UUID,
        quantity: float,
        price_per_unit: float | None = None,
        currency: str = "EUR",
        terms: dict[str, Any] | None = None,
        valid_until: datetime | None = None,
        notes: str | None = None,
    ) -> RecoveryProposal:
        # A coordinator may only propose on behalf of their own organisation.
        self._permit_roles(frozenset({ActorRole.COORDINATOR}), operation="create", entity_type="proposal")
        if not self.actor.platform_scope and self.actor.organization_id is None:
            raise ForbiddenError(
                "Select an active organisation before creating a proposal.",
                details={"reason": "organization_context_required"},
            )

        opportunity = self.session.get(RecoveryOpportunity, opportunity_id)
        if opportunity is None:
            raise NotFoundError("Opportunity not found.")

        if opportunity.compatibility_status == CompatibilityStatus.INCOMPATIBLE:
            raise ValidationError(
                "The compatibility engine rejected this pair; a proposal cannot be created.",
                code="opportunity_incompatible",
                details={"compatibility_status": opportunity.compatibility_status.value},
            )

        if not self.actor.is_platform_admin:
            parties = {
                opportunity.supplier_organization_id,
                opportunity.consumer_organization_id,
            }
            if self.actor.organization_id not in parties:
                # Record the attempt for the audit trail but answer 404: a tenant
                # must not be able to confirm that another tenant's opportunity
                # exists by comparing 403 with 404.
                audit.record_authorization_failure(
                    self.session,
                    actor_id=self.actor.actor_id,
                    actor_role=self.actor.role.value,
                    organization_id=self.actor.organization_id,
                    operation="create",
                    entity_type="proposal",
                    entity_id=opportunity.id,
                    required=None,
                )
                self.session.commit()
                raise NotFoundError("Opportunity not found.")

        if quantity <= 0:
            raise ValidationError(
                "Proposed quantity must be greater than zero.",
                code="quantity_invalid",
                details={"quantity": quantity},
            )
        if float(quantity) > float(opportunity.match_quantity):
            raise ValidationError(
                "Proposed quantity exceeds the screened match quantity.",
                code="quantity_exceeds_match",
                details={
                    "quantity": quantity,
                    "match_quantity": float(opportunity.match_quantity),
                },
            )

        proposal = RecoveryProposal(
            opportunity_id=opportunity.id,
            proposed_by_organization_id=opportunity.supplier_organization_id,
            receiving_organization_id=opportunity.consumer_organization_id,
            quantity=quantity,
            unit=opportunity.unit,
            price_per_unit=price_per_unit,
            currency=currency.upper(),
            status=ProposalStatus.DRAFT,
            compatibility_status=opportunity.compatibility_status,
            terms=terms or {},
            valid_until=valid_until,
            notes=notes,
            is_demo=opportunity.is_demo,
            version=0,
        )
        self.session.add(proposal)
        self.session.flush()

        audit.record_event(
            self.session,
            event_type="proposal.created",
            entity_type=TransitionEntity.PROPOSAL.value,
            entity_id=proposal.id,
            actor=self.actor.actor_id,
            actor_id=self.actor.actor_id,
            organization_id=proposal.proposed_by_organization_id,
            previous_state=None,
            new_state=ProposalStatus.DRAFT.value,
            summary="Proposal created in draft.",
            payload={
                "opportunity_id": str(opportunity.id),
                "quantity": float(proposal.quantity),
                "unit": proposal.unit.value,
                "compatibility_status": proposal.compatibility_status.value,
            },
        )
        self._commit()
        return proposal

    # ------------------------------------------------------------------
    # proposal transitions
    # ------------------------------------------------------------------
    def apply_proposal_action(
        self,
        proposal_id: uuid.UUID,
        *,
        action: str,
        reason: str | None = None,
        approval_reference: str | None = None,
        evidence: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> RecoveryProposal:
        proposal = self.get_proposal(proposal_id, lock=True)
        rule = lifecycle.proposal_rule(proposal.status, action)
        if rule is None:
            raise InvalidTransitionError(
                f"'{action}' is not a valid action for a proposal in status "
                f"'{proposal.status.value}'.",
                details={
                    "status": proposal.status.value,
                    "action": action,
                    "allowed_actions": lifecycle.available_proposal_actions(proposal.status),
                },
            )
        if rule.internal_only:
            raise ForbiddenError(
                f"'{action}' is driven by the transaction workflow and cannot be requested directly.",
                details={"action": action, "reason": "internal_action"},
            )

        self._check_version(proposal.version, expected_version, entity="proposal")
        cleaned_reason = _normalise_reason(reason)

        if rule.requires_reason and not cleaned_reason:
            raise EvidenceRequiredError(
                f"A reason is required to {action.replace('_', ' ')} a proposal.",
                details={"field": "reason", "action": action},
            )
        if rule.requires_evidence:
            reference = (approval_reference or "").strip()
            if len(reference) < 3:
                raise EvidenceRequiredError(
                    "Approval requires an evidence reference (for example a signed decision id).",
                    details={"field": "approval_reference", "action": action},
                )
            # Segregation of duties: a submitter may never decide their own proposal.
            if proposal.submitted_by and proposal.submitted_by == self.actor.actor_id:
                self._deny(
                    operation=action,
                    entity_type="proposal",
                    entity_id=proposal.id,
                    reason="segregation_of_duties",
                )
            proposal.approval_reference = reference
            proposal.approval_evidence = dict(evidence or {}, reference=reference)

        self._authorize_rule(rule, proposal.proposed_by_organization_id, proposal.receiving_organization_id, entity_type="proposal", entity_id=proposal.id, operation=action)
        self._apply_rule(proposal, rule, entity_type="proposal", reason=cleaned_reason)
        self._commit()
        return proposal

    # ------------------------------------------------------------------
    # transactions
    # ------------------------------------------------------------------
    def create_transaction(
        self,
        *,
        proposal_id: uuid.UUID,
        carrier_name: str | None = None,
        transport_distance_km: float | None = None,
        transfer_reference: str | None = None,
        notes: str | None = None,
    ) -> RecoveryTransaction:
        self._permit_roles(
            frozenset({ActorRole.COORDINATOR, ActorRole.APPROVER}),
            operation="create",
            entity_type="transaction",
        )
        proposal = self.get_proposal(proposal_id, lock=True)

        # Duplicate prevention comes first: a second attempt on a proposal that
        # already has a transaction is a conflict, not a state-machine error.
        existing_id = self.session.scalar(
            select(RecoveryTransaction.id).where(
                RecoveryTransaction.proposal_id == proposal.id
            )
        )
        if existing_id is not None:
            raise ConflictError(
                "This proposal already has a transaction.",
                details={"transaction_id": str(existing_id)},
            )

        if proposal.status != ProposalStatus.APPROVED:
            raise InvalidTransitionError(
                "A transaction can only be created for an approved proposal.",
                details={
                    "status": proposal.status.value,
                    "required_status": ProposalStatus.APPROVED.value,
                },
            )

        transaction = RecoveryTransaction(
            proposal_id=proposal.id,
            status=TransactionStatus.CREATED,
            source_organization_id=proposal.proposed_by_organization_id,
            destination_organization_id=proposal.receiving_organization_id,
            accepted_quantity=proposal.quantity,
            unit=proposal.unit,
            carrier_name=carrier_name,
            transport_distance_km=transport_distance_km,
            transfer_reference=transfer_reference,
            notes=notes,
            evidence={},
            is_demo=proposal.is_demo,
            version=0,
        )
        self.session.add(transaction)
        try:
            self.session.flush()
        except IntegrityError as exc:  # concurrent duplicate creation
            self.session.rollback()
            raise ConflictError(
                "This proposal already has a transaction.",
                details={"reason": "duplicate_transaction"},
            ) from exc

        audit.record_event(
            self.session,
            event_type="transaction.created",
            entity_type=TransitionEntity.TRANSACTION.value,
            entity_id=transaction.id,
            actor=self.actor.actor_id,
            actor_id=self.actor.actor_id,
            organization_id=transaction.source_organization_id,
            previous_state=None,
            new_state=TransactionStatus.CREATED.value,
            summary="Transaction created from an approved proposal.",
            payload={
                "proposal_id": str(proposal.id),
                "accepted_quantity": float(proposal.quantity),
                "unit": proposal.unit.value,
                "source_organization_id": str(transaction.source_organization_id),
                "destination_organization_id": str(transaction.destination_organization_id),
            },
        )

        # The proposal moves into execution as part of the same transaction.
        self._apply_proposal_side_effect(
            proposal,
            "start",
            reason="Transaction created.",
            context={"transaction_id": str(transaction.id)},
        )
        self._commit()
        return transaction

    def record_transfer(
        self,
        transaction_id: uuid.UUID,
        *,
        transferred_quantity: float,
        transfer_reference: str,
        material_identification: str,
        transferred_at: datetime | None = None,
        carrier_name: str | None = None,
        transport_distance_km: float | None = None,
        evidence: dict[str, Any] | None = None,
        notes: str | None = None,
        expected_version: int | None = None,
    ) -> RecoveryTransaction:
        transaction = self.get_transaction(transaction_id, lock=True)
        rule = lifecycle.transaction_rule(transaction.status, "record_transfer")
        if rule is None:
            raise InvalidTransitionError(
                f"'record-transfer' is not valid for a transaction in status "
                f"'{transaction.status.value}'.",
                details={
                    "status": transaction.status.value,
                    "allowed_actions": lifecycle.available_transaction_actions(
                        transaction.status
                    ),
                },
            )
        self._authorize_rule(
            rule,
            transaction.source_organization_id,
            transaction.destination_organization_id,
            entity_type="transaction",
            entity_id=transaction.id,
            operation="record_transfer",
        )
        self._check_version(transaction.version, expected_version, entity="transaction")

        if transferred_quantity is None or float(transferred_quantity) <= 0:
            raise ValidationError(
                "Transferred quantity must be greater than zero.",
                code="quantity_invalid",
                details={"transferred_quantity": transferred_quantity},
            )
        if not (transfer_reference or "").strip():
            raise EvidenceRequiredError(
                "A transfer reference (weighbridge ticket, delivery note) is required.",
                details={"field": "transfer_reference"},
            )
        if not (material_identification or "").strip():
            raise EvidenceRequiredError(
                "A material identification is required for the transfer.",
                details={"field": "material_identification"},
            )
        accepted = float(transaction.accepted_quantity or 0.0)
        if accepted and float(transferred_quantity) > accepted:
            raise ValidationError(
                "Transferred quantity cannot exceed the contracted quantity.",
                code="quantity_exceeds_contract",
                details={
                    "transferred_quantity": float(transferred_quantity),
                    "accepted_quantity": accepted,
                },
            )

        recorded_at = transferred_at or _utcnow()
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        if recorded_at > _utcnow():
            raise ValidationError(
                "The transfer date cannot be in the future.",
                code="transfer_date_invalid",
            )

        transaction.transferred_quantity = transferred_quantity
        transaction.transferred_at = recorded_at
        transaction.transfer_recorded_by = self.actor.actor_id
        transaction.transfer_reference = transfer_reference.strip()
        transaction.material_identification = material_identification.strip()
        if carrier_name:
            transaction.carrier_name = carrier_name
        if transport_distance_km is not None:
            transaction.transport_distance_km = transport_distance_km
        if transaction.dispatched_at is None:
            transaction.dispatched_at = recorded_at
        if evidence:
            transaction.evidence = {**dict(transaction.evidence or {}), **evidence}
        if notes:
            transaction.notes = notes

        self._apply_rule(
            transaction,
            rule,
            entity_type="transaction",
            reason=None,
            context={
                "transferred_quantity": float(transferred_quantity),
                "transfer_reference": transaction.transfer_reference,
                "material_identification": transaction.material_identification,
            },
        )
        self._commit()
        return transaction

    def verify_transaction(
        self,
        transaction_id: uuid.UUID,
        *,
        verified_quantity: float,
        verification_method: VerificationMethod,
        evidence_reference: str,
        evidence: dict[str, Any] | None = None,
        notes: str | None = None,
        expected_version: int | None = None,
    ) -> RecoveryTransaction:
        transaction = self.get_transaction(transaction_id, lock=True)
        rule = lifecycle.transaction_rule(transaction.status, "verify")
        if rule is None:
            raise InvalidTransitionError(
                f"'verify' is not valid for a transaction in status "
                f"'{transaction.status.value}'.",
                details={
                    "status": transaction.status.value,
                    "allowed_actions": lifecycle.available_transaction_actions(
                        transaction.status
                    ),
                },
            )
        self._authorize_rule(
            rule,
            transaction.source_organization_id,
            transaction.destination_organization_id,
            entity_type="transaction",
            entity_id=transaction.id,
            operation="verify",
        )
        self._check_version(transaction.version, expected_version, entity="transaction")

        if transaction.transferred_quantity is None or transaction.transferred_at is None:
            raise EvidenceRequiredError(
                "The physical transfer must be recorded before it can be verified.",
                details={"field": "transferred_quantity"},
            )
        if verified_quantity is None or float(verified_quantity) <= 0:
            raise ValidationError(
                "Verified quantity must be greater than zero.",
                code="quantity_invalid",
                details={"verified_quantity": verified_quantity},
            )
        if float(verified_quantity) > float(transaction.transferred_quantity):
            raise ValidationError(
                "Verified quantity cannot exceed the recorded transferred quantity.",
                code="quantity_exceeds_transfer",
                details={
                    "verified_quantity": float(verified_quantity),
                    "transferred_quantity": float(transaction.transferred_quantity),
                },
            )
        reference = (evidence_reference or "").strip()
        if len(reference) < 3:
            raise EvidenceRequiredError(
                "Verification requires an evidence reference such as a weighbridge ticket id.",
                details={"field": "evidence_reference"},
            )
        if verification_method is None:
            raise EvidenceRequiredError(
                "A verification method is required.",
                details={"field": "verification_method"},
            )
        if transaction.transfer_recorded_by == self.actor.actor_id:
            self._deny(
                operation="verify",
                entity_type="transaction",
                entity_id=transaction.id,
                reason="segregation_of_duties",
            )

        transaction.verified_quantity = verified_quantity
        transaction.verified_at = _utcnow()
        transaction.verified_by = self.actor.actor_id
        transaction.verification_method = verification_method
        transaction.evidence = {
            **dict(transaction.evidence or {}),
            **dict(evidence or {}),
            "verification_reference": reference,
            "verified_by": self.actor.actor_id,
            "verified_at": transaction.verified_at.isoformat(),
        }
        if notes:
            transaction.notes = notes

        self._apply_rule(
            transaction,
            rule,
            entity_type="transaction",
            reason=None,
            context={
                "verified_quantity": float(verified_quantity),
                "verification_method": verification_method.value,
                "evidence_reference": reference,
            },
        )
        self._apply_proposal_side_effect(
            transaction.proposal,
            "complete",
            reason="Transaction verified.",
            context={"transaction_id": str(transaction.id)},
        )
        self._commit()
        return transaction

    def reject_transaction(
        self,
        transaction_id: uuid.UUID,
        *,
        reason: str,
        expected_version: int | None = None,
    ) -> RecoveryTransaction:
        return self._exception_transaction(
            transaction_id, "reject", reason=reason, expected_version=expected_version
        )

    def cancel_transaction(
        self,
        transaction_id: uuid.UUID,
        *,
        reason: str,
        expected_version: int | None = None,
    ) -> RecoveryTransaction:
        return self._exception_transaction(
            transaction_id, "cancel", reason=reason, expected_version=expected_version
        )

    def _exception_transaction(
        self,
        transaction_id: uuid.UUID,
        action: str,
        *,
        reason: str,
        expected_version: int | None,
    ) -> RecoveryTransaction:
        transaction = self.get_transaction(transaction_id, lock=True)
        rule = lifecycle.transaction_rule(transaction.status, action)
        if rule is None:
            raise InvalidTransitionError(
                f"'{action}' is not valid for a transaction in status "
                f"'{transaction.status.value}'.",
                details={
                    "status": transaction.status.value,
                    "allowed_actions": lifecycle.available_transaction_actions(
                        transaction.status
                    ),
                },
            )
        self._authorize_rule(
            rule,
            transaction.source_organization_id,
            transaction.destination_organization_id,
            entity_type="transaction",
            entity_id=transaction.id,
            operation=action,
        )
        self._check_version(transaction.version, expected_version, entity="transaction")
        cleaned = _normalise_reason(reason)
        if not cleaned or len(cleaned) < 5:
            raise EvidenceRequiredError(
                f"A reason of at least 5 characters is required to {action} a transaction.",
                details={"field": "reason", "action": action},
            )

        self._apply_rule(
            transaction, rule, entity_type="transaction", reason=cleaned
        )
        proposal = self.session.get(RecoveryProposal, transaction.proposal_id)
        if proposal is not None:
            if action == "reject" and proposal.status in {
                ProposalStatus.APPROVED,
                ProposalStatus.IN_PROGRESS,
            }:
                self._apply_proposal_side_effect(
                    proposal,
                    "fail",
                    reason=f"Transaction rejected: {cleaned}",
                    context={"transaction_id": str(transaction.id)},
                )
            elif action == "cancel" and proposal.status in {
                ProposalStatus.APPROVED,
                ProposalStatus.IN_PROGRESS,
            }:
                self._apply_proposal_side_effect(
                    proposal,
                    "cancel",
                    reason=f"Transaction cancelled: {cleaned}",
                    context={"transaction_id": str(transaction.id)},
                )
        self._commit()
        return transaction

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _apply_proposal_side_effect(
        self,
        proposal: RecoveryProposal,
        action: str,
        *,
        reason: str | None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """System-driven proposal transition triggered by the transaction workflow."""
        rule = lifecycle.proposal_rule(proposal.status, action)
        if rule is None:
            raise InvalidTransitionError(
                f"Proposal workflow cannot apply '{action}' from '{proposal.status.value}'.",
                details={
                    "status": proposal.status.value,
                    "action": action,
                },
            )
        self._apply_rule(
            proposal,
            rule,
            entity_type="proposal",
            reason=reason,
            context=context,
        )

    def _apply_rule(
        self,
        record: RecoveryProposal | RecoveryTransaction,
        rule: TransitionRule,
        *,
        entity_type: str,
        reason: str | None,
        context: dict[str, Any] | None = None,
    ) -> None:
        previous = rule.from_state
        new_state = rule.to_state
        setattr(record, "status", new_state)

        timestamp_field = rule.sets_timestamp
        if timestamp_field:
            setattr(record, timestamp_field, _utcnow())

        key = (entity_type, rule.action)
        actor_field = _ACTOR_FIELDS.get(key)
        if actor_field:
            setattr(record, actor_field, self.actor.actor_id)
        reason_field = _REASON_FIELDS.get(key)
        if reason_field and reason:
            setattr(record, reason_field, reason)

        record.version = int(record.version or 0) + 1

        transition = StatusTransition(
            entity_type=TransitionEntity(entity_type),
            entity_id=record.id,
            action=rule.action,
            from_state=previous.value,
            to_state=new_state.value,
            actor_id=self.actor.actor_id,
            actor_role=self.actor.role,
            organization_id=self.actor.organization_id,
            reason=reason,
            context=context or {},
            occurred_at=_utcnow(),
        )
        self.session.add(transition)

        audit.record_event(
            self.session,
            event_type=f"{entity_type}.{rule.action}",
            entity_type=entity_type,
            entity_id=record.id,
            actor=self.actor.actor_id,
            actor_id=self.actor.actor_id,
            organization_id=self.actor.organization_id,
            previous_state=previous.value,
            new_state=new_state.value,
            reason=reason,
            summary=f"{entity_type.capitalize()} {previous.value} → {new_state.value} ({rule.action}).",
            payload={
                "action": rule.action,
                "actor_role": self.actor.role.value,
                "actor_display_name": self.actor.display_name,
                **(context or {}),
            },
        )

    def _authorize_rule(
        self,
        rule: TransitionRule,
        source_organization_id: uuid.UUID,
        destination_organization_id: uuid.UUID,
        *,
        entity_type: str,
        entity_id: uuid.UUID | None,
        operation: str,
    ) -> None:
        self._permit_roles(
            rule.roles,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        # Platform-scope actors may act across organisations for permitted roles.
        # Org-scoped actors (including reviewer/approver/auditor members) may only
        # act for participant organisations relevant to the rule.
        if self.actor.platform_scope:
            return
        allowed = {source_organization_id, destination_organization_id}
        if rule.party == Party.PROPOSING:
            allowed = {source_organization_id}
        elif rule.party == Party.RECEIVING:
            allowed = {destination_organization_id}
        if self.actor.organization_id not in allowed:
            self._deny(
                operation=operation,
                entity_type=entity_type,
                entity_id=entity_id,
                reason="organisation_scope",
            )

    def _permit_roles(
        self,
        roles: frozenset[ActorRole],
        *,
        operation: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
    ) -> None:
        if self.actor.role == ActorRole.ADMIN or self.actor.role in roles:
            return
        self._deny(
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            reason="insufficient_role",
            required=sorted(role.value for role in roles),
        )

    def _deny(
        self,
        *,
        operation: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        reason: str,
        required: list[str] | None = None,
    ) -> None:
        """Persist the denied attempt, then raise 403."""
        audit.record_authorization_failure(
            self.session,
            actor_id=self.actor.actor_id,
            actor_role=self.actor.role.value,
            organization_id=self.actor.organization_id,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
            required=required,
        )
        self.session.commit()
        raise ForbiddenError(
            "You are not authorized to perform this action.",
            details={"operation": operation, "reason": reason},
        )

    def _check_version(
        self, current: int, expected: int | None, *, entity: str
    ) -> None:
        if expected is None:
            return
        if int(expected) != int(current):
            raise VersionConflictError(
                "This record changed since you loaded it. Refresh and try again.",
                details={"entity": entity, "expected_version": expected, "current_version": current},
            )

    def _commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    # ------------------------------------------------------------------
    # read helpers
    # ------------------------------------------------------------------
    def available_actions(
        self, record: RecoveryProposal | RecoveryTransaction
    ) -> list[str]:
        """Actions this actor may attempt right now (used by the UI)."""
        if isinstance(record, RecoveryProposal):
            actions = lifecycle.available_proposal_actions(record.status)
            rules = [
                lifecycle.proposal_rule(record.status, action) for action in actions
            ]
            source, destination = (
                record.proposed_by_organization_id,
                record.receiving_organization_id,
            )
            return [
                rule.action
                for rule in rules
                if rule is not None
                and self._may_act(rule, source, destination, record, "proposal")
            ]

        actions = lifecycle.available_transaction_actions(record.status)
        rules = [lifecycle.transaction_rule(record.status, action) for action in actions]
        source, destination = (
            record.source_organization_id,
            record.destination_organization_id,
        )
        return [
            rule.action
            for rule in rules
            if rule is not None
            and self._may_act(rule, source, destination, record, "transaction")
        ]

    def _may_act(
        self,
        rule: TransitionRule,
        source_organization_id: uuid.UUID,
        destination_organization_id: uuid.UUID,
        record: RecoveryProposal | RecoveryTransaction,
        entity_type: str,
    ) -> bool:
        if self.actor.role != ActorRole.ADMIN and self.actor.role not in rule.roles:
            return False
        if not self.actor.platform_scope:
            # Keep the advertised actions identical to what _authorize_rule will
            # accept, for every org-scoped role, so the client never sees an
            # action it cannot perform.
            allowed = {source_organization_id, destination_organization_id}
            if rule.party == Party.PROPOSING:
                allowed = {source_organization_id}
            elif rule.party == Party.RECEIVING:
                allowed = {destination_organization_id}
            if self.actor.organization_id not in allowed:
                return False
        if entity_type == "proposal" and rule.action == "approve":
            assert isinstance(record, RecoveryProposal)
            if record.submitted_by == self.actor.actor_id:
                return False
        if entity_type == "transaction" and rule.action == "verify":
            assert isinstance(record, RecoveryTransaction)
            if record.transfer_recorded_by == self.actor.actor_id:
                return False
        return True

    def proposal_history(self, proposal_id: uuid.UUID) -> Sequence[StatusTransition]:
        return list(
            self.session.scalars(
                select(StatusTransition)
                .where(
                    StatusTransition.entity_type == TransitionEntity.PROPOSAL,
                    StatusTransition.entity_id == proposal_id,
                )
                .order_by(StatusTransition.occurred_at, StatusTransition.created_at)
            ).all()
        )

    def transaction_history(
        self, transaction_id: uuid.UUID
    ) -> Sequence[StatusTransition]:
        return list(
            self.session.scalars(
                select(StatusTransition)
                .where(
                    StatusTransition.entity_type == TransitionEntity.TRANSACTION,
                    StatusTransition.entity_id == transaction_id,
                )
                .order_by(StatusTransition.occurred_at, StatusTransition.created_at)
            ).all()
        )


def proposal_list_statement() -> Select:
    return select(RecoveryProposal).options(
        joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.material),
        joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.supplier),
        joinedload(RecoveryProposal.opportunity).joinedload(RecoveryOpportunity.consumer),
        joinedload(RecoveryProposal.transaction),
    )


def transaction_list_statement() -> Select:
    return select(RecoveryTransaction).options(
        joinedload(RecoveryTransaction.proposal)
        .joinedload(RecoveryProposal.opportunity)
        .joinedload(RecoveryOpportunity.material),
        joinedload(RecoveryTransaction.source_organization),
        joinedload(RecoveryTransaction.destination_organization),
    )


def count_statement(statement: Select) -> Select:
    """Turn an entity select into a count select, keeping its filters."""
    return select(func.count()).select_from(statement.order_by(None).subquery())
