"""Read models for platform administration, tenant health and audit review.

Everything here is deliberately bounded: a platform operator sees aggregates and
safe operational metadata, never tenant business records (materials, demands,
proposals, transactions). Each function used by a paginated endpoint performs a
fixed number of grouped queries over the page's organisation ids, so the console
cannot produce an N+1 scan of the whole database.

Nothing in this module authorises anything. The endpoint layer resolves the
platform principal and refuses before calling in.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.enums import (
    AuditSeverity,
    InvitationStatus,
    MembershipRole,
    MembershipStatus,
    OrganizationStatus,
)
from app.db.models.audit import AuditEvent
from app.db.models.identity import Invitation, OrganizationMembership, User
from app.db.models.organization import Organization

#: Events the platform console treats as administrative or security-relevant.
ADMIN_CHANGE_EVENTS: frozenset[str] = frozenset(
    {
        "membership.changed",
        "membership.deactivated",
        "membership.reactivated",
        "membership.created",
        "invitation.created",
        "invitation.revoked",
        "platform.organization.suspended",
        "platform.organization.reactivated",
        "auth.password_reset_issued",
        "auth.sessions_revoked",
        "auth.password_changed",
        "auth.account_locked",
    }
)

SECURITY_EVENTS: frozenset[str] = frozenset(
    {
        "auth.login_failed",
        "auth.account_locked",
        "auth.password_reset_issued",
        "auth.sessions_revoked",
        "auth.password_changed",
        "auth.csrf_rejected",
        "auth.session_revoked",
    }
)

#: Keys whose values must never cross the serialisation boundary.
SENSITIVE_KEY = re.compile(
    r"(password|passwd|token|secret|hash|credential|api[_-]?key|authorization|cookie|session|recovery[_-]?code|otp|totp)",
    re.IGNORECASE,
)

#: `auth.*` payloads are reduced to these keys; anything else is dropped.
AUTH_PAYLOAD_ALLOWLIST: frozenset[str] = frozenset(
    {"outcome", "reason", "known_account", "delivery", "method"}
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _count(session: Session, stmt) -> int:
    return int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def redact_payload(event_type: str, payload: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Return a safe copy of an audit payload and the paths that were redacted.

    Two layers apply:

    * ``auth.*`` payloads keep only an explicit allow-list of non-sensitive keys,
      so a future field such as a reset link or a token cannot leak by accident;
    * every remaining key is checked against :data:`SENSITIVE_KEY` recursively,
      and long strings are truncated so a single event cannot bloat a response.

    The stored row is never modified: this function works on a copy.
    """
    if not payload:
        return {}, []

    redacted: list[str] = []
    auth_event = event_type.startswith("auth.")

    def walk(value: Any, path: str, depth: int) -> Any:
        if depth > 5:
            redacted.append(path or ".")
            return "[truncated]"
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else key
                if auth_event and key not in AUTH_PAYLOAD_ALLOWLIST:
                    redacted.append(child_path)
                    continue
                if SENSITIVE_KEY.search(str(key)):
                    redacted.append(child_path)
                    result[key] = "[redacted]"
                    continue
                result[key] = walk(item, child_path, depth + 1)
            return result
        if isinstance(value, list):
            return [walk(item, f"{path}[{index}]", depth + 1) for index, item in enumerate(value)]
        if isinstance(value, str):
            return value if len(value) <= 500 else f"{value[:500]}…[truncated]"
        return value

    safe = walk(payload, "", 0)
    return (safe if isinstance(safe, dict) else {}), sorted(set(redacted))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DashboardData:
    organisation_counts: dict[str, int] = field(default_factory=dict)
    user_counts: dict[str, int] = field(default_factory=dict)
    membership_counts: dict[str, int] = field(default_factory=dict)
    pending_invitations: int = 0
    failed_logins_window: int = 0
    organisations_created_window: int = 0
    recent_organisations: Sequence[Organization] = ()
    recent_events: Sequence[AuditEvent] = ()


def dashboard_data(
    session: Session, *, window_days: int = 30, failure_hours: int = 24
) -> DashboardData:
    now = utcnow()
    window_start = now - timedelta(days=window_days)
    failure_start = now - timedelta(hours=failure_hours)

    organisation_counts = {
        status.value: count
        for status, count in session.execute(
            select(Organization.status, func.count(Organization.id)).group_by(Organization.status)
        ).all()
    }
    user_counts = {
        "total": _count(session, select(User.id)),
        "active": _count(session, select(User.id).where(User.is_active.is_(True))),
    }
    membership_counts = {
        status.value: count
        for status, count in session.execute(
            select(OrganizationMembership.status, func.count(OrganizationMembership.id)).group_by(
                OrganizationMembership.status
            )
        ).all()
    }
    pending_invitations = _count(
        session,
        select(Invitation.id).where(
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > now,
        ),
    )
    failed_logins_window = _count(
        session,
        select(AuditEvent.id).where(
            AuditEvent.event_type == "auth.login_failed",
            AuditEvent.created_at >= failure_start,
        ),
    )
    organisations_created_window = _count(
        session,
        select(Organization.id).where(Organization.created_at >= window_start),
    )

    recent_organisations = session.scalars(
        select(Organization).order_by(Organization.created_at.desc(), Organization.id.asc()).limit(6)
    ).all()

    recent_events = session.scalars(
        select(AuditEvent)
        .where(
            or_(
                AuditEvent.event_type.in_(ADMIN_CHANGE_EVENTS),
                AuditEvent.severity.in_([AuditSeverity.WARNING, AuditSeverity.CRITICAL]),
            )
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(8)
    ).all()

    return DashboardData(
        organisation_counts=organisation_counts,
        user_counts=user_counts,
        membership_counts=membership_counts,
        pending_invitations=pending_invitations,
        failed_logins_window=failed_logins_window,
        organisations_created_window=organisations_created_window,
        recent_organisations=recent_organisations,
        recent_events=recent_events,
    )


# ---------------------------------------------------------------------------
# Organisation register
# ---------------------------------------------------------------------------


def like_pattern(value: str) -> str:
    """Escape SQL wildcards so a search box cannot become a table scan trick."""
    escaped = value.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def list_organisations(
    session: Session,
    *,
    offset: int,
    limit: int,
    q: str | None = None,
    status: OrganizationStatus | None = None,
) -> tuple[list[Organization], int, dict[uuid.UUID, dict[str, int]]]:
    stmt = select(Organization)
    if q:
        pattern = like_pattern(q)
        stmt = stmt.where(
            or_(
                func.lower(Organization.name).like(pattern, escape="\\"),
                func.lower(Organization.slug).like(pattern, escape="\\"),
                func.lower(func.coalesce(Organization.city, "")).like(pattern, escape="\\"),
            )
        )
    if status is not None:
        stmt = stmt.where(Organization.status == status)

    total = _count(session, stmt)
    organisations = list(
        session.scalars(
            stmt.order_by(Organization.created_at.desc(), Organization.id.asc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return organisations, total, membership_summary(session, [row.id for row in organisations])


def membership_summary(
    session: Session, organisation_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    """Active/suspended/pending counts for a bounded set of organisations."""
    ids = list(organisation_ids)
    if not ids:
        return {}

    summary: dict[uuid.UUID, dict[str, int]] = {
        org_id: {"active_members": 0, "suspended_members": 0, "pending_invitations": 0}
        for org_id in ids
    }
    for org_id, status, count in session.execute(
        select(
            OrganizationMembership.organization_id,
            OrganizationMembership.status,
            func.count(OrganizationMembership.id),
        )
        .where(OrganizationMembership.organization_id.in_(ids))
        .group_by(OrganizationMembership.organization_id, OrganizationMembership.status)
    ).all():
        key = "active_members" if status == MembershipStatus.ACTIVE else "suspended_members"
        if status in {MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED}:
            summary[org_id][key] = int(count)

    now = utcnow()
    for org_id, count in session.execute(
        select(Invitation.organization_id, func.count(Invitation.id))
        .where(
            Invitation.organization_id.in_(ids),
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > now,
        )
        .group_by(Invitation.organization_id)
    ).all():
        summary[org_id]["pending_invitations"] = int(count)

    return summary


def organisation_detail(session: Session, organisation: Organization) -> dict[str, Any]:
    """Operational snapshot for one organisation. No business records."""
    org_id = organisation.id
    now = utcnow()

    membership_counts = {
        status.value: count
        for status, count in session.execute(
            select(OrganizationMembership.status, func.count(OrganizationMembership.id))
            .where(OrganizationMembership.organization_id == org_id)
            .group_by(OrganizationMembership.status)
        ).all()
    }
    invitation_counts = {
        status.value: count
        for status, count in session.execute(
            select(Invitation.status, func.count(Invitation.id))
            .where(Invitation.organization_id == org_id)
            .group_by(Invitation.status)
        ).all()
    }
    # Pending and expired partition the same status, so the two numbers never
    # double-count an invitation that is still open but past its expiry.
    live_invitations = _count(
        session,
        select(Invitation.id).where(
            Invitation.organization_id == org_id,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at > now,
        ),
    )
    expired_invitations = _count(
        session,
        select(Invitation.id).where(
            Invitation.organization_id == org_id,
            Invitation.status == InvitationStatus.PENDING,
            Invitation.expires_at <= now,
        ),
    )
    active_administrators = _count(
        session,
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.role == MembershipRole.ORG_ADMIN,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        ),
    )
    last_event_at = session.scalar(
        select(func.max(AuditEvent.created_at)).where(AuditEvent.organization_id == org_id)
    )
    recent_events = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == org_id,
            or_(
                AuditEvent.event_type.in_(ADMIN_CHANGE_EVENTS),
                AuditEvent.severity.in_([AuditSeverity.WARNING, AuditSeverity.CRITICAL]),
            ),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(8)
    ).all()

    active_members = int(membership_counts.get(MembershipStatus.ACTIVE.value, 0))
    warnings = _warnings(
        organisation=organisation,
        active_members=active_members,
        active_administrators=active_administrators,
    )

    return {
        "members": {
            "active": active_members,
            "suspended": int(membership_counts.get(MembershipStatus.SUSPENDED.value, 0)),
            "invited": int(membership_counts.get(MembershipStatus.INVITED.value, 0)),
            "removed": int(membership_counts.get(MembershipStatus.REMOVED.value, 0)),
        },
        "invitations": {
            "pending": live_invitations,
            "expired": expired_invitations,
            "accepted": int(invitation_counts.get(InvitationStatus.ACCEPTED.value, 0)),
            "revoked": int(invitation_counts.get(InvitationStatus.REVOKED.value, 0)),
        },
        "administrators": {"active": active_administrators},
        "last_activity_at": _as_utc(last_event_at),
        "warnings": warnings,
        "state": _state(organisation, warnings),
        "checks": _CHECKS,
        "recent_events": recent_events,
    }


_CHECKS: tuple[str, ...] = (
    "tenant_active",
    "membership_present",
    "active_administrator_present",
)


def _warnings(
    *, organisation: Organization, active_members: int, active_administrators: int
) -> list[str]:
    warnings: list[str] = []
    if organisation.status == OrganizationStatus.SUSPENDED:
        warnings.append("organization_suspended")
    if active_members == 0:
        warnings.append("no_active_members")
    if active_administrators == 0:
        warnings.append("no_active_administrator")
    return warnings


def _state(organisation: Organization, warnings: list[str]) -> str:
    if organisation.status == OrganizationStatus.SUSPENDED:
        return "suspended"
    return "attention" if warnings else "ok"


# ---------------------------------------------------------------------------
# Tenant health
# ---------------------------------------------------------------------------


def tenant_health_page(
    session: Session, *, offset: int, limit: int, window_days: int = 30, failure_days: int = 7
) -> tuple[list[dict[str, Any]], int]:
    """One page of organisations with bounded, honestly-labelled indicators."""
    now = utcnow()
    window_start = now - timedelta(days=window_days)
    failure_start = now - timedelta(days=failure_days)

    total = _count(session, select(Organization.id))
    organisations = list(
        session.scalars(
            select(Organization)
            .order_by(Organization.created_at.desc(), Organization.id.asc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    ids = [row.id for row in organisations]
    if not ids:
        return [], total

    summary = membership_summary(session, ids)

    active_administrators = {
        org_id: int(count)
        for org_id, count in session.execute(
            select(OrganizationMembership.organization_id, func.count(OrganizationMembership.id))
            .where(
                OrganizationMembership.organization_id.in_(ids),
                OrganizationMembership.role == MembershipRole.ORG_ADMIN,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
            )
            .group_by(OrganizationMembership.organization_id)
        ).all()
    }
    admin_changes = {
        org_id: int(count)
        for org_id, count in session.execute(
            select(AuditEvent.organization_id, func.count(AuditEvent.id))
            .where(
                AuditEvent.organization_id.in_(ids),
                AuditEvent.created_at >= window_start,
                AuditEvent.event_type.in_(ADMIN_CHANGE_EVENTS),
            )
            .group_by(AuditEvent.organization_id)
        ).all()
    }
    security_events = {
        org_id: int(count)
        for org_id, count in session.execute(
            select(AuditEvent.organization_id, func.count(AuditEvent.id))
            .where(
                AuditEvent.organization_id.in_(ids),
                AuditEvent.created_at >= window_start,
                or_(
                    AuditEvent.event_type.in_(SECURITY_EVENTS),
                    AuditEvent.severity.in_([AuditSeverity.WARNING, AuditSeverity.CRITICAL]),
                ),
            )
            .group_by(AuditEvent.organization_id)
        ).all()
    }
    last_activity = {
        org_id: _as_utc(last)
        for org_id, last in session.execute(
            select(AuditEvent.organization_id, func.max(AuditEvent.created_at))
            .where(AuditEvent.organization_id.in_(ids))
            .group_by(AuditEvent.organization_id)
        ).all()
    }

    # Failed sign-ins carry no tenant on the event itself (the tenant is unknown
    # until authentication succeeds), so they are attributed by account
    # membership and labelled as such in the response and the console.
    member_failures = {
        org_id: int(count)
        for org_id, count in session.execute(
            select(OrganizationMembership.organization_id, func.count(AuditEvent.id))
            .join(
                AuditEvent,
                and_(
                    AuditEvent.entity_id == OrganizationMembership.user_id,
                    AuditEvent.event_type == "auth.login_failed",
                    AuditEvent.created_at >= failure_start,
                ),
            )
            .where(OrganizationMembership.organization_id.in_(ids))
            .group_by(OrganizationMembership.organization_id)
        ).all()
    }

    rows: list[dict[str, Any]] = []
    for organisation in organisations:
        counts = summary.get(
            organisation.id,
            {"active_members": 0, "suspended_members": 0, "pending_invitations": 0},
        )
        admins = active_administrators.get(organisation.id, 0)
        warnings = _warnings(
            organisation=organisation,
            active_members=counts["active_members"],
            active_administrators=admins,
        )
        rows.append(
            {
                "organization": organisation,
                "active_members": counts["active_members"],
                "suspended_members": counts["suspended_members"],
                "pending_invitations": counts["pending_invitations"],
                "active_administrators": admins,
                "admin_changes_window": admin_changes.get(organisation.id, 0),
                "security_events_window": security_events.get(organisation.id, 0),
                "member_auth_failures_window": member_failures.get(organisation.id, 0),
                "last_activity_at": last_activity.get(organisation.id),
                "state": _state(organisation, warnings),
                "warnings": warnings,
                "checks": list(_CHECKS),
            }
        )
    return rows, total


# ---------------------------------------------------------------------------
# Audit journal
# ---------------------------------------------------------------------------


def audit_events(
    session: Session,
    *,
    offset: int,
    limit: int,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    actor_id: str | None = None,
    actor: str | None = None,
    organization_id: uuid.UUID | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    order: str = "desc",
) -> tuple[list[AuditEvent], int]:
    stmt = select(AuditEvent)
    if created_from is not None:
        stmt = stmt.where(AuditEvent.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(AuditEvent.created_at <= created_to)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if actor:
        stmt = stmt.where(
            func.lower(AuditEvent.actor).like(like_pattern(actor), escape="\\")
        )
    if organization_id is not None:
        stmt = stmt.where(AuditEvent.organization_id == organization_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if target_user_id is not None:
        # User events address the user directly; membership events address the
        # membership row. Both are resolved to the target account here so the
        # operator does not have to know internal identifiers.
        membership_ids = select(OrganizationMembership.id).where(
            OrganizationMembership.user_id == target_user_id
        )
        stmt = stmt.where(
            or_(
                and_(
                    AuditEvent.entity_type == "user",
                    AuditEvent.entity_id == target_user_id,
                ),
                and_(
                    AuditEvent.entity_type.in_(["membership", "organization_membership"]),
                    AuditEvent.entity_id.in_(membership_ids),
                ),
            )
        )

    total = _count(session, stmt)
    if order == "asc":
        ordering = (AuditEvent.created_at.asc(), AuditEvent.id.asc())
    else:
        ordering = (AuditEvent.created_at.desc(), AuditEvent.id.desc())
    events = list(
        session.scalars(stmt.order_by(*ordering).offset(offset).limit(limit)).all()
    )
    return events, total


def organization_names(session: Session, events: Sequence[AuditEvent]) -> dict[uuid.UUID, str]:
    """Resolve organisation names for one page of audit events in one query."""
    ids = {event.organization_id for event in events if event.organization_id is not None}
    if not ids:
        return {}
    return {
        org_id: name
        for org_id, name in session.execute(
            select(Organization.id, Organization.name).where(Organization.id.in_(ids))
        ).all()
    }
