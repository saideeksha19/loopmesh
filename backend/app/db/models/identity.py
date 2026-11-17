"""Identity, membership and session persistence.

Phase 2B replaces the development actor registry with real users.

Design notes:

* A user is a person, never a tenant. Tenancy lives in
  :class:`OrganizationMembership`, and a user may hold memberships in several
  organisations with different roles.
* Only token *hashes* are stored. A database leak therefore does not hand an
  attacker a usable session or invitation link.
* Memberships, sessions and invitations all carry explicit status values so
  suspension and revocation are data, not deletions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.enums import (
    InvitationStatus,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
    enum_column_type,
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An authenticated person."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("length(email) >= 5", name="email_present"),
        CheckConstraint("failed_login_attempts >= 0", name="failed_attempts_non_negative"),
        CheckConstraint("mfa_failed_attempts >= 0", name="mfa_failed_attempts_non_negative"),
    )

    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)

    # Argon2id encoded hash. Never serialised by any schema.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(nullable=False, default=False)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Platform operator MFA. The TOTP secret is stored encrypted (Fernet) and is
    # never returned after enrolment; ``mfa_enrolled_at`` is set only once the
    # operator has confirmed a valid code. ``mfa_last_counter`` prevents a code
    # from being replayed on another session.
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_counter: Mapped[int | None] = mapped_column(Integer)
    mfa_failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    mfa_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="OrganizationMembership.user_id",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email}>"


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user's role inside one organisation."""

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="user_organization"),
        CheckConstraint(
            "accepted_at IS NULL OR created_at IS NULL OR accepted_at >= created_at",
            name="acceptance_after_creation",
        ),
        Index("ix_memberships_organization_role_status", "organization_id", "role", "status"),
        Index("ix_memberships_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MembershipRole] = mapped_column(
        enum_column_type(MembershipRole), nullable=False, index=True
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_column_type(MembershipStatus),
        nullable=False,
        default=MembershipStatus.INVITED,
        index=True,
    )
    scope: Mapped[MembershipScope] = mapped_column(
        enum_column_type(MembershipScope),
        nullable=False,
        default=MembershipScope.ORGANIZATION,
    )

    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invitations.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(
        "User",
        back_populates="memberships",
        foreign_keys=[user_id],
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Membership {self.user_id}@{self.organization_id} {self.role.value}>"


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A server-side session holding one rotating refresh-token family.

    Access and refresh tokens are random 256-bit values; only their SHA-256
    hashes are stored. Revocation is therefore immediate and provable.
    """

    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "access_expires_at > created_at", name="access_expiry_after_creation"
        ),
        CheckConstraint(
            "refresh_expires_at > access_expires_at", name="refresh_outlives_access"
        ),
        Index("ix_auth_sessions_user_active", "user_id", "revoked_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL")
    )

    access_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    refresh_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Double-submit CSRF secret, stored hashed like every other credential.
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(64))

    # Set only after a valid TOTP or recovery code. Platform routes require it;
    # rotation copies it forward so a refresh cannot be used to skip MFA.
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_method: Mapped[str | None] = mapped_column(String(16))
    replaced_by_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="SET NULL")
    )


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An administrator-issued invitation to join one organisation."""

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        Index("ix_invitations_email_status", "email", "status"),
    )

    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MembershipRole] = mapped_column(
        enum_column_type(MembershipRole), nullable=False
    )
    scope: Mapped[MembershipScope] = mapped_column(
        enum_column_type(MembershipScope),
        nullable=False,
        default=MembershipScope.ORGANIZATION,
    )
    status: Mapped[InvitationStatus] = mapped_column(
        enum_column_type(InvitationStatus),
        nullable=False,
        default=InvitationStatus.PENDING,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class MfaRecoveryCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use recovery code for a platform operator.

    Only a hash is stored. A code is consumed by setting ``used_at``; it is
    never deleted on use, so the audit trail of recovery attempts stays intact.
    """

    __tablename__ = "mfa_recovery_codes"
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="user_recovery_code"),
        Index("ix_mfa_recovery_codes_user_used", "user_id", "used_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordResetToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use password reset token (hash only)."""

    __tablename__ = "password_reset_tokens"
    __table_args__ = (CheckConstraint("expires_at > created_at", name="expiry_after_creation"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip_hash: Mapped[str | None] = mapped_column(String(64))
