"""ORM model registry.

Importing this package registers every table on ``Base.metadata``; Alembic and
the test fixtures rely on that.
"""

from app.db.models.agent import AgentExecution
from app.db.models.audit import AuditEvent, AuditIntegrityState
from app.db.models.demand import ResourceDemand
from app.db.models.identity import (
    AuthSession,
    Invitation,
    MfaRecoveryCode,
    OrganizationMembership,
    PasswordResetToken,
    User,
)
from app.db.models.material import Material, MaterialSpecification
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.db.models.platform_approval import PlatformApprovalRequest
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.db.models.security import AuditArchiveBatch, SecurityRateLimit
from app.db.models.transition import StatusTransition

__all__ = [
    "AgentExecution",
    "AuditArchiveBatch",
    "AuditEvent",
    "AuditIntegrityState",
    "AuthSession",
    "Invitation",
    "MfaRecoveryCode",
    "OrganizationMembership",
    "PasswordResetToken",
    "PlatformApprovalRequest",
    "User",
    "Material",
    "MaterialSpecification",
    "Organization",
    "RecoveryOpportunity",
    "RecoveryProposal",
    "RecoveryTransaction",
    "ResourceDemand",
    "SecurityRateLimit",
    "StatusTransition",
]
