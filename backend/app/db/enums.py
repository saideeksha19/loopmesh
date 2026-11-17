"""Domain enumerations.

Every enum is persisted as a constrained ``VARCHAR`` (``native_enum=False``)
so the schema behaves identically on PostgreSQL and SQLite and future value
additions stay a simple migration.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum


def enum_column_type(enum_cls: type[enum.Enum]) -> SAEnum:
    """Build a portable, CHECK-constrained column type for a string enum."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=32,
        values_callable=lambda cls: [member.value for member in cls],
    )


class OrganizationSector(str, enum.Enum):
    CHEMICALS = "chemicals"
    STEEL_METALS = "steel_metals"
    CEMENT_MINERALS = "cement_minerals"
    FOOD_AGRICULTURE = "food_agriculture"
    PLASTICS_POLYMERS = "plastics_polymers"
    TEXTILES = "textiles"
    GLASS_CERAMICS = "glass_ceramics"
    PAPER_PACKAGING = "paper_packaging"
    ENERGY_UTILITIES = "energy_utilities"
    CONSTRUCTION = "construction"
    LOGISTICS = "logistics"
    WATER_TREATMENT = "water_treatment"
    OTHER = "other"


class MaterialCategory(str, enum.Enum):
    METALS = "metals"
    POLYMERS = "polymers"
    MINERALS = "minerals"
    ORGANICS = "organics"
    CHEMICALS = "chemicals"
    GLASS = "glass"
    PAPER = "paper"
    TEXTILES = "textiles"
    WATER = "water"
    ENERGY = "energy"
    OTHER = "other"


class MaterialUnit(str, enum.Enum):
    KILOGRAM = "kg"
    TONNE = "tonne"
    CUBIC_METRE = "m3"
    LITRE = "litre"
    MEGAWATT_HOUR = "mwh"


class MaterialCondition(str, enum.Enum):
    AS_GENERATED = "as_generated"
    PROCESSED = "processed"
    AGED = "aged"
    DEGRADED = "degraded"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MaterialStatus(str, enum.Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    COMMITTED = "committed"
    DEPLETED = "depleted"
    ARCHIVED = "archived"


class OrganizationStatus(str, enum.Enum):
    """Operational state of a tenant, set only by platform administration.

    Suspension is not deletion: memberships, invitations, sessions and business
    records survive. It removes the organisation from every authentication and
    authorisation path until it is reactivated.
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"


class ApprovalAction(str, enum.Enum):
    """High-impact platform operations that require two operators."""

    SUSPEND = "suspend"
    REACTIVATE = "reactivate"


class ApprovalStatus(str, enum.Enum):
    """Lifecycle of a platform approval request.

    ``executed``, ``rejected``, ``cancelled`` and ``expired`` are terminal and
    cannot be revived; a fresh request is the only way to try again.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    EXECUTED = "executed"


class DataSource(str, enum.Enum):
    """How a material record entered the system."""

    DEMO = "demo"
    FORM = "form"
    CSV = "csv"
    DOCUMENT = "document"


class DemandStatus(str, enum.Enum):
    OPEN = "open"
    PAUSED = "paused"
    FULFILLED = "fulfilled"
    CLOSED = "closed"


class DemandFrequency(str, enum.Enum):
    ONE_OFF = "one_off"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    CONTINUOUS = "continuous"


class CompatibilityStatus(str, enum.Enum):
    COMPATIBLE = "compatible"
    CONDITIONAL = "conditional"
    INCOMPATIBLE = "incompatible"
    UNVERIFIED = "unverified"


class OpportunityStatus(str, enum.Enum):
    IDENTIFIED = "identified"
    SCREENING = "screening"
    SHORTLISTED = "shortlisted"
    CONVERTED = "converted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ProposalStatus(str, enum.Enum):
    """Proposal lifecycle. Terminal states cannot be reopened."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    # Exception / terminal states
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TransactionStatus(str, enum.Enum):
    """Physical recovery transaction lifecycle.

    ``failed`` is retained as a reserved terminal state for integrations that
    report an operation-level failure; the Phase 2A API reaches ``rejected``,
    ``cancelled`` and ``verified`` only.
    """

    CREATED = "created"
    IN_PROGRESS = "in_progress"
    TRANSFERRED = "transferred"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


class VerificationMethod(str, enum.Enum):
    WEIGHBRIDGE_TICKET = "weighbridge_ticket"
    THIRD_PARTY_AUDIT = "third_party_audit"
    SUPPLIER_DECLARATION = "supplier_declaration"
    LABORATORY_ASSAY = "laboratory_assay"
    OTHER = "other"


class AgentName(str, enum.Enum):
    MATERIAL_ANALYST = "material_analyst"
    RESOURCE_SCOUT = "resource_scout"
    COMPATIBILITY_ASSESSOR = "compatibility_assessor"
    OPTIMIZATION_PLANNER = "optimization_planner"
    RECOVERY_COORDINATOR = "recovery_coordinator"


class AgentRunStatus(str, enum.Enum):
    NOT_ENABLED = "not_enabled"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ActorRole(str, enum.Enum):
    """Effective role used by the workflow state machine.

    Resolved server-side from an authenticated user's active organisation
    membership. ``admin`` is reserved for platform administrators; an
    organisation administrator resolves to ``org_admin`` and does not receive
    platform-wide authority.
    """

    ADMIN = "admin"
    ORG_ADMIN = "org_admin"
    COORDINATOR = "coordinator"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class MembershipRole(str, enum.Enum):
    """Role held inside one organisation."""

    ORG_ADMIN = "org_admin"
    COORDINATOR = "coordinator"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class MembershipStatus(str, enum.Enum):
    """Membership lifecycle. Only ``active`` grants any authority."""

    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class MembershipScope(str, enum.Enum):
    """How far a membership's authority reaches.

    ``organization`` limits every action to records where the member's own
    organisation is a party. ``platform`` is an explicit, separately granted
    scope that lets a role act across organisations (for example a platform
    auditor verifying a transaction between two other companies).
    """

    ORGANIZATION = "organization"
    PLATFORM = "platform"


class MfaMethod(str, enum.Enum):
    """How the current session proved a second factor."""

    TOTP = "totp"
    RECOVERY = "recovery"


class InvitationStatus(str, enum.Enum):
    """Invitation lifecycle."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class TransitionEntity(str, enum.Enum):
    """Entities that carry an explicit lifecycle state machine."""

    PROPOSAL = "proposal"
    TRANSACTION = "transaction"


class LedgerState(str, enum.Enum):
    """Legacy four-state recovery view kept for API compatibility."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    TRANSPORTED = "transported"
    VERIFIED = "verified"
