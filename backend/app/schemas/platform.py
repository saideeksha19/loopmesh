"""Schemas for platform administration, tenant health and audit review.

These are deliberately separate from the organisation-workspace schemas: the
platform console must not accidentally grow a field that leaks tenant business
content, and an organisation schema must not acquire platform-only fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.enums import ApprovalAction, ApprovalStatus, OrganizationStatus
from app.schemas.common import ApiModel


class PlatformOrganizationSummary(ApiModel):
    id: UUID
    name: str
    slug: str
    sector: str
    country: str
    city: str | None = None
    status: OrganizationStatus
    is_demo: bool = False
    created_at: datetime
    suspended_at: datetime | None = None


class PlatformOrganizationRead(PlatformOrganizationSummary):
    active_members: int = 0
    suspended_members: int = 0
    pending_invitations: int = 0


class PlatformMembershipCounts(BaseModel):
    active: int = 0
    suspended: int = 0
    invited: int = 0
    removed: int = 0


class PlatformInvitationCounts(BaseModel):
    pending: int = 0
    expired: int = 0
    accepted: int = 0
    revoked: int = 0


class PlatformAuditSummary(ApiModel):
    """Compact, payload-free event shape for dashboards and detail panels."""

    id: UUID
    created_at: datetime
    event_type: str
    entity_type: str
    entity_id: UUID | None = None
    actor: str
    severity: str
    summary: str
    organization_id: UUID | None = None
    organization_name: str | None = None


class PlatformOrganizationDetail(PlatformOrganizationSummary):
    members: PlatformMembershipCounts
    invitations: PlatformInvitationCounts
    administrators: dict[str, int]
    last_activity_at: datetime | None = None
    state: str
    warnings: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    recent_events: list[PlatformAuditSummary] = Field(default_factory=list)


class PlatformOrganizationUpdate(BaseModel):
    """The only mutable platform field is the tenant lifecycle state.

    ``extra="forbid"`` makes an attempted name/slug/sector edit a validation
    error rather than a silently ignored field.
    """

    model_config = ConfigDict(extra="forbid")

    status: OrganizationStatus
    reason: str | None = Field(default=None, max_length=400)
    # Required for every protected transition: a status change executes an
    # approved request and cannot be performed by a single operator.
    approval_id: UUID | None = Field(
        default=None, description="Approved two-person request authorising this change."
    )


class PlatformDashboardCounts(BaseModel):
    total: int = 0
    active: int = 0
    suspended: int = 0
    created_in_window: int = 0


class PlatformUserCounts(BaseModel):
    total: int = 0
    active: int = 0


class PlatformDashboard(BaseModel):
    generated_at: datetime
    window_days: int
    failure_window_hours: int
    organisations: PlatformDashboardCounts
    users: PlatformUserCounts
    memberships: PlatformMembershipCounts
    pending_invitations: int = 0
    failed_logins_window: int = 0
    recent_organisations: list[PlatformOrganizationSummary] = Field(default_factory=list)
    recent_events: list[PlatformAuditSummary] = Field(default_factory=list)


class PlatformTenantHealth(BaseModel):
    organization: PlatformOrganizationSummary
    active_members: int = 0
    suspended_members: int = 0
    pending_invitations: int = 0
    active_administrators: int = 0
    admin_changes_window: int = 0
    security_events_window: int = 0
    member_auth_failures_window: int = 0
    last_activity_at: datetime | None = None
    state: str
    warnings: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class PlatformApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    action: ApprovalAction
    reason: str | None = Field(default=None, max_length=400)


class PlatformApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=400)


class PlatformApprovalRead(BaseModel):
    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    organization_slug: str | None = None
    organization_status: OrganizationStatus | None = None
    action: ApprovalAction
    reason: str | None = None
    status: ApprovalStatus
    requested_by_user_id: UUID
    requested_by: str | None = None
    created_at: datetime
    expires_at: datetime
    decided_by_user_id: UUID | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None
    executed_by_user_id: UUID | None = None
    executed_by: str | None = None
    executed_at: datetime | None = None
    is_expired: bool = False
    can_decide: bool = False
    can_execute: bool = False
    can_cancel: bool = False


class PlatformApprovalExecuteResult(BaseModel):
    approval: PlatformApprovalRead
    organization: PlatformOrganizationSummary


class PlatformOperatorSession(BaseModel):
    id: UUID
    user_id: UUID
    user_email: EmailStr
    created_at: datetime
    last_seen_at: datetime | None = None
    mfa_verified_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    is_current: bool = False
    user_agent: str | None = None


class PlatformSessionRevocation(BaseModel):
    message: str
    revoked_count: int = 0


class PlatformAuditIntegrity(BaseModel):
    valid: bool
    checked: int
    first_invalid_sequence: int | None = None
    reason: str | None = None
    chain_head: str
    state_sequence: int
    state_hash: str
    verified_at: datetime


class PlatformAuditEvent(BaseModel):
    id: UUID
    created_at: datetime
    event_type: str
    entity_type: str
    entity_id: UUID | None = None
    actor: str
    actor_id: str | None = None
    organization_id: UUID | None = None
    organization_name: str | None = None
    severity: str
    summary: str
    reason: str | None = None
    previous_state: str | None = None
    new_state: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    redacted_fields: list[str] = Field(default_factory=list)
