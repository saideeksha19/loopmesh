"""Organisation member administration schemas.

Read models expose only the fields a member administrator needs. Password
hashes, session tokens, invitation token hashes and platform flags never leave
the database through these endpoints.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import ApiModel


class MemberRead(ApiModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    role: str
    scope: str
    status: str
    joined_at: datetime | None = None
    is_self: bool = False


class MemberUpdateRequest(ApiModel):
    """A role and/or scope change; any other submitted field is ignored."""

    role: str | None = None
    scope: str | None = None


class MemberActionRead(ApiModel):
    member: MemberRead
    sessions_revoked: int = 0


class MemberResetRead(ApiModel):
    member: MemberRead
    sessions_revoked: int
    must_change_password: bool
    message: str
