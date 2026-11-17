"""Central lifecycle definitions for proposals and transactions.

This module is the single source of truth for:

* which transitions exist,
* who may perform them,
* which fields they require,
* which timestamp/evidence fields they set,
* which states are terminal.

Nothing here mutates data; :mod:`app.services.workflow` applies these rules.
Any endpoint or agent that wants a state change must go through that service,
so an invalid or unauthorised transition cannot bypass the machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.db.enums import ActorRole, ProposalStatus, TransactionStatus


class Party(str, Enum):
    """Which side of the proposal may perform an action."""

    PROPOSING = "proposing"
    RECEIVING = "receiving"
    EITHER = "either"


@dataclass(frozen=True, slots=True)
class TransitionRule:
    action: str
    from_state: Enum
    to_state: Enum
    roles: frozenset[ActorRole]
    party: Party
    requires_reason: bool = False
    requires_evidence: bool = False
    sets_timestamp: str | None = None
    internal_only: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (str(self.from_state.value), self.action)


def _roles(*roles: ActorRole) -> frozenset[ActorRole]:
    return frozenset(roles)


REVIEWERS = _roles(ActorRole.REVIEWER, ActorRole.APPROVER)
APPROVERS = _roles(ActorRole.APPROVER)
COORDINATORS = _roles(ActorRole.COORDINATOR)
AUDITORS = _roles(ActorRole.AUDITOR, ActorRole.APPROVER)

PROPOSAL_TRANSITIONS: tuple[TransitionRule, ...] = (
    # --- draft -------------------------------------------------------------
    TransitionRule(
        action="submit",
        from_state=ProposalStatus.DRAFT,
        to_state=ProposalStatus.SUBMITTED,
        roles=COORDINATORS,
        party=Party.PROPOSING,
        sets_timestamp="submitted_at",
    ),
    TransitionRule(
        action="withdraw",
        from_state=ProposalStatus.DRAFT,
        to_state=ProposalStatus.WITHDRAWN,
        roles=COORDINATORS,
        party=Party.PROPOSING,
        sets_timestamp="withdrawn_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=ProposalStatus.DRAFT,
        to_state=ProposalStatus.CANCELLED,
        roles=_roles(),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    # --- submitted ---------------------------------------------------------
    TransitionRule(
        action="review",
        from_state=ProposalStatus.SUBMITTED,
        to_state=ProposalStatus.UNDER_REVIEW,
        roles=REVIEWERS,
        party=Party.RECEIVING,
        sets_timestamp="reviewed_at",
    ),
    TransitionRule(
        action="reject",
        from_state=ProposalStatus.SUBMITTED,
        to_state=ProposalStatus.REJECTED,
        roles=REVIEWERS,
        party=Party.RECEIVING,
        requires_reason=True,
        sets_timestamp="rejected_at",
    ),
    TransitionRule(
        action="withdraw",
        from_state=ProposalStatus.SUBMITTED,
        to_state=ProposalStatus.WITHDRAWN,
        roles=COORDINATORS,
        party=Party.PROPOSING,
        sets_timestamp="withdrawn_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=ProposalStatus.SUBMITTED,
        to_state=ProposalStatus.CANCELLED,
        roles=_roles(),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    # --- under review ------------------------------------------------------
    TransitionRule(
        action="approve",
        from_state=ProposalStatus.UNDER_REVIEW,
        to_state=ProposalStatus.APPROVED,
        roles=APPROVERS,
        party=Party.RECEIVING,
        requires_evidence=True,
        sets_timestamp="approved_at",
    ),
    TransitionRule(
        action="reject",
        from_state=ProposalStatus.UNDER_REVIEW,
        to_state=ProposalStatus.REJECTED,
        roles=REVIEWERS,
        party=Party.RECEIVING,
        requires_reason=True,
        sets_timestamp="rejected_at",
    ),
    TransitionRule(
        action="withdraw",
        from_state=ProposalStatus.UNDER_REVIEW,
        to_state=ProposalStatus.WITHDRAWN,
        roles=COORDINATORS,
        party=Party.PROPOSING,
        sets_timestamp="withdrawn_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=ProposalStatus.UNDER_REVIEW,
        to_state=ProposalStatus.CANCELLED,
        roles=_roles(),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    # --- approved ----------------------------------------------------------
    TransitionRule(
        action="start",
        from_state=ProposalStatus.APPROVED,
        to_state=ProposalStatus.IN_PROGRESS,
        roles=_roles(ActorRole.COORDINATOR, ActorRole.APPROVER),
        party=Party.EITHER,
        sets_timestamp="started_at",
        internal_only=True,
    ),
    TransitionRule(
        action="cancel",
        from_state=ProposalStatus.APPROVED,
        to_state=ProposalStatus.CANCELLED,
        roles=_roles(),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    TransitionRule(
        action="fail",
        from_state=ProposalStatus.APPROVED,
        to_state=ProposalStatus.FAILED,
        roles=_roles(ActorRole.AUDITOR),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="failed_at",
        internal_only=True,
    ),
    # --- in progress -------------------------------------------------------
    TransitionRule(
        action="complete",
        from_state=ProposalStatus.IN_PROGRESS,
        to_state=ProposalStatus.COMPLETED,
        roles=AUDITORS,
        party=Party.RECEIVING,
        sets_timestamp="completed_at",
        internal_only=True,
    ),
    TransitionRule(
        action="cancel",
        from_state=ProposalStatus.IN_PROGRESS,
        to_state=ProposalStatus.CANCELLED,
        roles=_roles(),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    TransitionRule(
        action="fail",
        from_state=ProposalStatus.IN_PROGRESS,
        to_state=ProposalStatus.FAILED,
        roles=_roles(ActorRole.AUDITOR),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="failed_at",
        internal_only=True,
    ),
)

TERMINAL_PROPOSAL_STATES: frozenset[ProposalStatus] = frozenset(
    {
        ProposalStatus.COMPLETED,
        ProposalStatus.REJECTED,
        ProposalStatus.WITHDRAWN,
        ProposalStatus.CANCELLED,
        ProposalStatus.FAILED,
    }
)

TRANSACTION_TRANSITIONS: tuple[TransitionRule, ...] = (
    TransitionRule(
        action="start",
        from_state=TransactionStatus.CREATED,
        to_state=TransactionStatus.IN_PROGRESS,
        roles=_roles(ActorRole.COORDINATOR, ActorRole.APPROVER),
        party=Party.EITHER,
        sets_timestamp="transfer_started_at",
    ),
    TransitionRule(
        action="record_transfer",
        from_state=TransactionStatus.CREATED,
        to_state=TransactionStatus.TRANSFERRED,
        roles=_roles(ActorRole.COORDINATOR, ActorRole.APPROVER),
        party=Party.EITHER,
        requires_evidence=False,
        sets_timestamp="transferred_at",
    ),
    TransitionRule(
        action="record_transfer",
        from_state=TransactionStatus.IN_PROGRESS,
        to_state=TransactionStatus.TRANSFERRED,
        roles=_roles(ActorRole.COORDINATOR, ActorRole.APPROVER),
        party=Party.EITHER,
        sets_timestamp="transferred_at",
    ),
    TransitionRule(
        action="verify",
        from_state=TransactionStatus.TRANSFERRED,
        to_state=TransactionStatus.VERIFIED,
        roles=AUDITORS,
        party=Party.RECEIVING,
        requires_evidence=True,
        sets_timestamp="verified_at",
    ),
    TransitionRule(
        action="reject",
        from_state=TransactionStatus.CREATED,
        to_state=TransactionStatus.REJECTED,
        roles=AUDITORS,
        party=Party.RECEIVING,
        requires_reason=True,
        sets_timestamp="rejected_at",
    ),
    TransitionRule(
        action="reject",
        from_state=TransactionStatus.IN_PROGRESS,
        to_state=TransactionStatus.REJECTED,
        roles=AUDITORS,
        party=Party.RECEIVING,
        requires_reason=True,
        sets_timestamp="rejected_at",
    ),
    TransitionRule(
        action="reject",
        from_state=TransactionStatus.TRANSFERRED,
        to_state=TransactionStatus.REJECTED,
        roles=AUDITORS,
        party=Party.RECEIVING,
        requires_reason=True,
        sets_timestamp="rejected_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=TransactionStatus.CREATED,
        to_state=TransactionStatus.CANCELLED,
        roles=_roles(ActorRole.COORDINATOR),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=TransactionStatus.IN_PROGRESS,
        to_state=TransactionStatus.CANCELLED,
        roles=_roles(ActorRole.COORDINATOR),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
    TransitionRule(
        action="cancel",
        from_state=TransactionStatus.TRANSFERRED,
        to_state=TransactionStatus.CANCELLED,
        roles=_roles(ActorRole.COORDINATOR),
        party=Party.EITHER,
        requires_reason=True,
        sets_timestamp="cancelled_at",
    ),
)

TERMINAL_TRANSACTION_STATES: frozenset[TransactionStatus] = frozenset(
    {
        TransactionStatus.VERIFIED,
        TransactionStatus.REJECTED,
        TransactionStatus.CANCELLED,
        TransactionStatus.FAILED,
    }
)

_PROPOSAL_INDEX: dict[tuple[str, str], TransitionRule] = {
    rule.key: rule for rule in PROPOSAL_TRANSITIONS
}
_TRANSACTION_INDEX: dict[tuple[str, str], TransitionRule] = {
    rule.key: rule for rule in TRANSACTION_TRANSITIONS
}

PROPOSAL_ACTIONS_BY_STATE: dict[str, list[str]] = {}
for _rule in PROPOSAL_TRANSITIONS:
    if _rule.internal_only:
        continue
    PROPOSAL_ACTIONS_BY_STATE.setdefault(str(_rule.from_state.value), [])
    if _rule.action not in PROPOSAL_ACTIONS_BY_STATE[str(_rule.from_state.value)]:
        PROPOSAL_ACTIONS_BY_STATE[str(_rule.from_state.value)].append(_rule.action)

TRANSACTION_ACTIONS_BY_STATE: dict[str, list[str]] = {}
for _rule in TRANSACTION_TRANSITIONS:
    TRANSACTION_ACTIONS_BY_STATE.setdefault(str(_rule.from_state.value), [])
    if _rule.action not in TRANSACTION_ACTIONS_BY_STATE[str(_rule.from_state.value)]:
        TRANSACTION_ACTIONS_BY_STATE[str(_rule.from_state.value)].append(_rule.action)


def proposal_rule(from_state: ProposalStatus, action: str) -> TransitionRule | None:
    return _PROPOSAL_INDEX.get((str(from_state.value), action))


def transaction_rule(from_state: TransactionStatus, action: str) -> TransitionRule | None:
    return _TRANSACTION_INDEX.get((str(from_state.value), action))


def available_proposal_actions(status: ProposalStatus) -> list[str]:
    """Actions exposed over HTTP for a proposal in this state."""
    return list(PROPOSAL_ACTIONS_BY_STATE.get(status.value, []))


def available_transaction_actions(status: TransactionStatus) -> list[str]:
    return list(TRANSACTION_ACTIONS_BY_STATE.get(status.value, []))


def state_machine_documentation() -> dict:
    """Machine-readable description used by docs and tests."""

    def serialise(rules: tuple[TransitionRule, ...]) -> list[dict]:
        return [
            {
                "action": rule.action,
                "from": str(rule.from_state.value),
                "to": str(rule.to_state.value),
                "roles": sorted(role.value for role in rule.roles) or ["admin only"],
                "party": rule.party.value,
                "requires_reason": rule.requires_reason,
                "requires_evidence": rule.requires_evidence,
                "internal_only": rule.internal_only,
            }
            for rule in rules
        ]

    return {
        "proposals": serialise(PROPOSAL_TRANSITIONS),
        "transactions": serialise(TRANSACTION_TRANSITIONS),
        "terminal_proposal_states": sorted(state.value for state in TERMINAL_PROPOSAL_STATES),
        "terminal_transaction_states": sorted(
            state.value for state in TERMINAL_TRANSACTION_STATES
        ),
    }
