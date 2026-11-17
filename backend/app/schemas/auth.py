"""Authentication and session schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    organization_id: UUID | None = Field(
        default=None,
        description="Preferred active organisation for this session.",
    )


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    new_password: str = Field(min_length=8, max_length=256)


class SwitchOrganizationRequest(BaseModel):
    organization_id: UUID


class MfaEnrollRequest(BaseModel):
    """Enrolment is a re-authenticated action, not a bare session call."""

    current_password: str = Field(min_length=1, max_length=256)


class MfaEnrollResponse(BaseModel):
    secret: str
    provisioning_uri: str
    message: str


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaConfirmResponse(BaseModel):
    message: str
    recovery_codes: list[str]
    enrolled_at: datetime


class MfaFactorRequest(BaseModel):
    """One factor: a TOTP code or a single-use recovery code."""

    code: str | None = Field(default=None, max_length=64)
    recovery_code: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_factor(self) -> "MfaFactorRequest":
        if bool(self.code) == bool(self.recovery_code):
            raise ValueError("Provide exactly one of code or recovery_code.")
        return self


class MfaDisableRequest(MfaFactorRequest):
    current_password: str = Field(min_length=1, max_length=256)


class MfaRegenerateRequest(MfaFactorRequest):
    current_password: str = Field(min_length=1, max_length=256)


class MfaRegenerateResponse(BaseModel):
    message: str
    recovery_codes: list[str]


class MfaStatus(BaseModel):
    enrolled: bool = False
    verified: bool = False
    required: bool = False
    enrollment_required: bool = False
    recovery_codes_remaining: int = 0
    locked_until: datetime | None = None
    method: str | None = None


class InvitationCreateRequest(BaseModel):
    email: EmailStr
    organization_id: UUID
    role: str = Field(min_length=1, max_length=32)
    scope: str = Field(default="organization", min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=1000)


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=256)


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    role: str
    scope: str
    status: str
    organization_name: str | None = None
    organization_slug: str | None = None


class SessionRead(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    created_at: datetime
    last_seen_at: datetime | None = None
    access_expires_at: datetime
    refresh_expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    is_current: bool = False
    user_agent: str | None = None
    mfa_verified_at: datetime | None = None


class InvitationRead(BaseModel):
    id: UUID
    email: EmailStr
    organization_id: UUID
    organization_name: str | None = None
    role: str
    scope: str
    status: str
    expires_at: datetime
    created_at: datetime
    invited_by_user_id: UUID | None = None
    accepted_at: datetime | None = None
    note: str | None = None
    # Development-only: populated only by the dev delivery adapter when explicitly enabled.
    delivery_token: str | None = None


class MeResponse(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_platform_admin: bool
    is_development: bool = False
    must_change_password: bool = False
    active_organization_id: UUID | None = None
    active_role: str | None = None
    memberships: list[MembershipRead] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    session_expires_at: datetime | None = None
    mfa_enrolled: bool = False
    mfa_verified: bool = False
    mfa_required: bool = False
    mfa_enrollment_required: bool = False
    csrf_token: str | None = Field(
        default=None,
        description="CSRF token for cookie-authenticated clients (double-submit).",
    )


class AuthMessage(BaseModel):
    message: str
    authenticated: bool = False
    user: MeResponse | None = None


class PasswordResetRequested(BaseModel):
    message: str
    # Development-only delivery token when no production email provider is configured.
    delivery_token: str | None = None
