"""Centralized tenant scoping and authorization helpers.

All organization-scoped reads and writes must pass through these helpers so
isolation rules are consistent and auditable. Deny by default.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from app.core.actors import ActorContext
from app.core.exceptions import ForbiddenError, NotFoundError


def require_active_organization(actor: ActorContext) -> uuid.UUID:
    """Return the actor's active organization or refuse with 403."""
    org_id = actor.organization_id
    if org_id is None:
        raise ForbiddenError(
            "Select an active organisation before performing this action.",
            details={"reason": "organization_context_required"},
        )
    return org_id


def resolve_requested_organization(
    actor: ActorContext,
    requested: uuid.UUID | None,
    *,
    operation: str = "access",
    allow_none: bool = True,
) -> uuid.UUID | None:
    """Validate a client-supplied organization filter/id.

    A client value is never proof of authorization. Platform-scope actors may
    request any organization; org-scoped actors may only request organizations
    they are an active member of (and, for writes, their active organization).
    """
    if requested is None:
        return None if allow_none else require_active_organization(actor)
    if actor.platform_scope:
        return requested
    if requested in actor.organization_ids:
        return requested
    raise ForbiddenError(
        "You do not have access to the requested organisation.",
        details={"reason": "organisation_scope", "operation": operation},
    )


def require_owned_organization(
    actor: ActorContext, organization_id: uuid.UUID, *, operation: str = "access"
) -> uuid.UUID:
    """Require that the actor may act for this specific organization."""
    if actor.platform_scope:
        return organization_id
    # For mutations we bind to the active organization to prevent acting across
    # memberships without an explicit organization switch.
    if actor.organization_id == organization_id and organization_id in actor.organization_ids:
        return organization_id
    raise ForbiddenError(
        "You do not have access to this organisation.",
        details={"reason": "organisation_scope", "operation": operation},
    )


def ensure_visible_parties(
    actor: ActorContext, organization_ids: Iterable[uuid.UUID], *, not_found: str = "Record not found."
) -> None:
    """Raise 404 when a private record is outside the actor's reach.

    404 avoids confirming existence to unrelated tenants.
    """
    ids = {oid for oid in organization_ids if oid is not None}
    if actor.sees_all_records:
        return
    if actor.organization_ids & ids:
        return
    raise NotFoundError(not_found)


def ensure_read_organization(
    actor: ActorContext, organization_id: uuid.UUID | None, *, not_found: str = "Record not found."
) -> None:
    if organization_id is None:
        return
    if actor.sees_all_records:
        return
    if organization_id in actor.organization_ids:
        return
    raise NotFoundError(not_found)
