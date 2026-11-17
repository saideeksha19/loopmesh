"""Central permission catalogue and role matrix.

Phase 2A authorised with role-name comparisons scattered across the workflow
service. That does not scale to organisation scoping, so every decision now
resolves to one of the permissions below.

Three rules make the model auditable:

* a permission is a *capability*, never a record;
* a role is a fixed set of permissions, declared in one table;
* record-level decisions (which organisation, which party, which scope) are
  made by :class:`app.core.actors.ActorContext`, never by role names.

Deny by default: anything not listed is refused.
"""

from __future__ import annotations

from enum import Enum

from app.db.enums import MembershipRole


class Permission(str, Enum):
    # platform administration — see PLATFORM_PERMISSIONS below
    PLATFORM_ADMIN = "platform.admin"
    PLATFORM_DASHBOARD_VIEW = "platform.dashboard.view"
    PLATFORM_ORGANIZATIONS_VIEW = "platform.organizations.view"
    PLATFORM_ORGANIZATIONS_MANAGE = "platform.organizations.manage"
    PLATFORM_AUDIT_VIEW = "platform.audit.view"
    PLATFORM_AUDIT_EXPORT = "platform.audit.export"
    PLATFORM_AUDIT_VERIFY = "platform.audit.verify"
    PLATFORM_AUDIT_ARCHIVE = "platform.audit.archive"
    PLATFORM_HEALTH_VIEW = "platform.health.view"
    PLATFORM_APPROVALS_VIEW = "platform.approvals.view"
    PLATFORM_APPROVALS_REQUEST = "platform.approvals.request"
    PLATFORM_APPROVALS_DECIDE = "platform.approvals.decide"
    PLATFORM_APPROVALS_EXECUTE = "platform.approvals.execute"
    PLATFORM_SESSIONS_MANAGE = "platform.sessions.manage"

    # organisation administration
    ORGANIZATION_VIEW = "organization.view"
    ORGANIZATION_MANAGE = "organization.manage"
    MEMBER_VIEW = "member.view"
    MEMBER_MANAGE = "member.manage"
    INVITATION_MANAGE = "invitation.manage"

    # material intelligence
    MATERIAL_VIEW = "material.view"
    MATERIAL_CREATE = "material.create"
    MATERIAL_IMPORT = "material.import"
    DEMAND_VIEW = "demand.view"
    OPPORTUNITY_VIEW = "opportunity.view"
    OPPORTUNITY_DISCOVER = "opportunity.discover"
    NETWORK_VIEW = "network.view"

    # lifecycle
    PROPOSAL_VIEW = "proposal.view"
    PROPOSAL_CREATE = "proposal.create"
    PROPOSAL_SUBMIT = "proposal.submit"
    PROPOSAL_WITHDRAW = "proposal.withdraw"
    PROPOSAL_REVIEW = "proposal.review"
    PROPOSAL_APPROVE = "proposal.approve"
    PROPOSAL_REJECT = "proposal.reject"
    PROPOSAL_CANCEL = "proposal.cancel"

    TRANSACTION_VIEW = "transaction.view"
    TRANSACTION_CREATE = "transaction.create"
    TRANSACTION_TRANSFER = "transaction.transfer"
    TRANSACTION_VERIFY = "transaction.verify"
    TRANSACTION_REJECT = "transaction.reject"
    TRANSACTION_CANCEL = "transaction.cancel"

    # reporting / oversight
    LEDGER_VIEW = "ledger.view"
    AUDIT_VIEW = "audit.view"
    DASHBOARD_VIEW = "dashboard.view"
    AGENT_VIEW = "agent.view"
    OPTIMIZATION_VIEW = "optimization.view"


_READ_ONLY: frozenset[Permission] = frozenset(
    {
        Permission.ORGANIZATION_VIEW,
        Permission.MEMBER_VIEW,
        Permission.MATERIAL_VIEW,
        Permission.DEMAND_VIEW,
        Permission.OPPORTUNITY_VIEW,
        Permission.NETWORK_VIEW,
        Permission.PROPOSAL_VIEW,
        Permission.TRANSACTION_VIEW,
        Permission.LEDGER_VIEW,
        Permission.DASHBOARD_VIEW,
        Permission.AGENT_VIEW,
        Permission.OPTIMIZATION_VIEW,
    }
)

ROLE_PERMISSIONS: dict[MembershipRole, frozenset[Permission]] = {
    MembershipRole.ORG_ADMIN: _READ_ONLY
    | frozenset(
        {
            Permission.ORGANIZATION_MANAGE,
            Permission.MEMBER_MANAGE,
            Permission.INVITATION_MANAGE,
            Permission.MATERIAL_CREATE,
            Permission.MATERIAL_IMPORT,
            Permission.OPPORTUNITY_DISCOVER,
            Permission.AUDIT_VIEW,
        }
    ),
    MembershipRole.COORDINATOR: _READ_ONLY
    | frozenset(
        {
            Permission.MATERIAL_CREATE,
            Permission.MATERIAL_IMPORT,
            Permission.OPPORTUNITY_DISCOVER,
            Permission.PROPOSAL_CREATE,
            Permission.PROPOSAL_SUBMIT,
            Permission.PROPOSAL_WITHDRAW,
            Permission.TRANSACTION_CREATE,
            Permission.TRANSACTION_TRANSFER,
        }
    ),
    MembershipRole.REVIEWER: _READ_ONLY
    | frozenset({Permission.PROPOSAL_REVIEW, Permission.PROPOSAL_REJECT}),
    MembershipRole.APPROVER: _READ_ONLY
    | frozenset(
        {
            Permission.PROPOSAL_REVIEW,
            Permission.PROPOSAL_REJECT,
            Permission.PROPOSAL_APPROVE,
            Permission.TRANSACTION_CREATE,
        }
    ),
    MembershipRole.AUDITOR: _READ_ONLY
    | frozenset(
        {
            Permission.AUDIT_VIEW,
            Permission.TRANSACTION_VERIFY,
            Permission.TRANSACTION_REJECT,
        }
    ),
    MembershipRole.VIEWER: _READ_ONLY,
}

#: The complete platform-administration catalogue.
#:
#: These capabilities are *structurally* unreachable from an organisation role:
#: no entry in ``ROLE_PERMISSIONS`` contains one, ``PLATFORM_PERMISSIONS`` is
#: disjoint from every role set (asserted at import time and in the test suite),
#: an organisation administrator cannot change its own membership or scope, and
#: Batch 10's member administration refuses to grant ``scope=platform`` to a
#: non-platform actor. They are held only through the explicit user-level
#: ``is_platform_admin`` flag, which no API endpoint can set.
PLATFORM_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PLATFORM_ADMIN,
        Permission.PLATFORM_DASHBOARD_VIEW,
        Permission.PLATFORM_ORGANIZATIONS_VIEW,
        Permission.PLATFORM_ORGANIZATIONS_MANAGE,
        Permission.PLATFORM_AUDIT_VIEW,
        Permission.PLATFORM_AUDIT_EXPORT,
        Permission.PLATFORM_AUDIT_VERIFY,
        Permission.PLATFORM_AUDIT_ARCHIVE,
        Permission.PLATFORM_HEALTH_VIEW,
        Permission.PLATFORM_APPROVALS_VIEW,
        Permission.PLATFORM_APPROVALS_REQUEST,
        Permission.PLATFORM_APPROVALS_DECIDE,
        Permission.PLATFORM_APPROVALS_EXECUTE,
        Permission.PLATFORM_SESSIONS_MANAGE,
    }
)

# Platform administrators get every permission; the flag is granted out-of-band
# (bootstrap CLI or another platform administrator), never by self-service.
ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)

if any(role_permissions & PLATFORM_PERMISSIONS for role_permissions in ROLE_PERMISSIONS.values()):
    raise RuntimeError(
        "An organisation role must never contain a platform-administration permission."
    )


def permissions_for(
    role: MembershipRole | None, *, platform_admin: bool = False
) -> frozenset[Permission]:
    """Resolve the capability set for a role."""
    if platform_admin:
        return ALL_PERMISSIONS
    if role is None:
        return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())


PROPOSAL_ACTION_PERMISSIONS: dict[str, Permission] = {
    "submit": Permission.PROPOSAL_SUBMIT,
    "withdraw": Permission.PROPOSAL_WITHDRAW,
    "review": Permission.PROPOSAL_REVIEW,
    "approve": Permission.PROPOSAL_APPROVE,
    "reject": Permission.PROPOSAL_REJECT,
    "cancel": Permission.PROPOSAL_CANCEL,
}

TRANSACTION_ACTION_PERMISSIONS: dict[str, Permission] = {
    "record_transfer": Permission.TRANSACTION_TRANSFER,
    "verify": Permission.TRANSACTION_VERIFY,
    "reject": Permission.TRANSACTION_REJECT,
    "cancel": Permission.TRANSACTION_CANCEL,
}
