"""Shared test fixtures: isolated SQLite database, API client and factories."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.enums import (
    CompatibilityStatus,
    DataSource,
    DemandFrequency,
    DemandStatus,
    MaterialCategory,
    MaterialCondition,
    MaterialStatus,
    MaterialUnit,
    OpportunityStatus,
    OrganizationSector,
    ProposalStatus,
    TransactionStatus,
    VerificationMethod,
)
from app.db.models.demand import ResourceDemand
from app.db.models.material import Material, MaterialSpecification
from app.db.models.opportunity import RecoveryOpportunity
from app.db.models.organization import Organization
from app.db.models.proposal import RecoveryProposal, RecoveryTransaction
from app.db.session import get_db
from app.main import app

TODAY = date.today()


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(session_factory: sessionmaker) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()



def _legacy_actor_for_header(db: Session, actor_id: str):
    """Test-only compatibility: map Phase 2A X-Actor-Id values to real principals.

    Exists solely to preserve legacy regression tests while production auth
    remains session-based. Never exposed outside the test dependency override.
    """
    from sqlalchemy import select
    from app.core.actors import build_principal
    from app.core.security import hash_password
    from app.db.enums import MembershipRole, MembershipScope, MembershipStatus
    from app.db.models.identity import OrganizationMembership, User
    from app.db.models.organization import Organization

    actor_id = (actor_id or "").strip().lower()
    if not actor_id:
        return None

    if actor_id in {"demo-platform-admin", "platform-admin", "admin"}:
        user = db.scalar(select(User).where(User.email == "legacy-platform-admin@example.com"))
        if user is None:
            user = User(email="legacy-platform-admin@example.com", full_name="Legacy Platform Admin", password_hash=hash_password("LegacyPass!2345"), is_active=True, is_platform_admin=True, password_changed_at=utcnow())
            db.add(user); db.flush()
        return build_principal(db, user=user, memberships=[])

    recognized_role = False
    role = None
    for key, val in {
        "coordinator": MembershipRole.COORDINATOR,
        "reviewer": MembershipRole.REVIEWER,
        "approver": MembershipRole.APPROVER,
        "auditor": MembershipRole.AUDITOR,
        "viewer": MembershipRole.VIEWER,
        "org-admin": MembershipRole.ORG_ADMIN,
        "org_admin": MembershipRole.ORG_ADMIN,
    }.items():
        if actor_id.endswith(key) or key in actor_id:
            role = val
            recognized_role = True
            break
    if not recognized_role:
        # Preserve legacy "observer/readonly" viewer aliases used in tests.
        if "observer" in actor_id or "readonly" in actor_id:
            role = MembershipRole.VIEWER
            recognized_role = True
    if role is None:
        return None

    orgs = db.scalars(select(Organization)).all()
    preferred = None
    tokens = [t for t in actor_id.replace("_", "-").split("-") if t and t not in {"coordinator","reviewer","approver","auditor","viewer","observer","readonly","org","admin","demo","platform"}]
    # Match on the organisation slug only. Organisation *names* are arbitrary in
    # fixtures (a cluster may name a `circulus-glass` org "Aurelia Chemicals"),
    # so name matching would silently place a legacy actor inside a record's
    # organisation and hide isolation defects.
    for org in orgs:
        if any(tok in org.slug.lower() for tok in tokens):
            preferred = org
            break
    if preferred is None:
        if "northgate" in actor_id:
            for org in orgs:
                if "meridian" in org.slug:
                    preferred = org; break
        if preferred is None:
            for key in ["aurelia","meridian","helios","northgate","solvane","limburg","circulus"]:
                if key in actor_id:
                    for org in orgs:
                        if key in org.slug:
                            preferred = org; break
                if preferred:
                    break
    known_org_keys = ["aurelia", "meridian", "helios", "northgate", "solvane", "limburg", "circulus"]
    home_key = next((k for k in known_org_keys if k in actor_id), None)
    is_global_legacy_role = role in {
        MembershipRole.REVIEWER,
        MembershipRole.APPROVER,
        MembershipRole.AUDITOR,
        MembershipRole.VIEWER,
        MembershipRole.ORG_ADMIN,
    }

    if preferred is None and recognized_role:
        # Coordinators remain org-scoped to their named/synthetic home org so
        # unrelated-record isolation tests behave correctly. Legacy reviewer/
        # approver/auditor/viewer actors were effectively global in Phase 2A and
        # need cross-org reach for regression coverage.
        if home_key is not None:
            for org in orgs:
                if home_key in org.slug.lower():
                    preferred = org
                    break
            if preferred is None:
                slug = f"legacy-{home_key}"
                existing = db.scalar(select(Organization).where(Organization.slug == slug))
                if existing is None:
                    existing = Organization(
                        name=f"Legacy {home_key.title()}",
                        slug=slug,
                        sector=OrganizationSector.CHEMICALS,
                        country="Netherlands",
                        city="Rotterdam",
                        is_demo=False,
                        data_source=DataSource.FORM,
                    )
                    db.add(existing)
                    db.flush()
                preferred = existing
        elif orgs:
            preferred = orgs[0] if role == MembershipRole.COORDINATOR else orgs[-1]
    if preferred is None and orgs and recognized_role:
        preferred = orgs[0] if role == MembershipRole.COORDINATOR else orgs[-1]
    if preferred is None:
        return None

    email = f"legacy-{actor_id}@example.com"
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, full_name=f"Legacy {actor_id}", password_hash=hash_password("LegacyPass!2345"), is_active=True, is_platform_admin=False, password_changed_at=utcnow())
        db.add(user); db.flush()

    membership_scope = MembershipScope.PLATFORM if is_global_legacy_role else MembershipScope.ORGANIZATION
    membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == preferred.id))
    if membership is None:
        membership = OrganizationMembership(user_id=user.id, organization_id=preferred.id, role=role, status=MembershipStatus.ACTIVE, scope=membership_scope)
        db.add(membership); db.flush()
    else:
        # Keep legacy test compatibility stable across repeated lookups.
        membership.role = role
        membership.status = MembershipStatus.ACTIVE
        membership.scope = membership_scope
        db.flush()
    memberships = db.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.status == MembershipStatus.ACTIVE)).all()
    return build_principal(db, user=user, auth_session=None, membership=membership, memberships=memberships)


@pytest.fixture()
def client(db: Session) -> Iterator[TestClient]:
    from app.core.exceptions import AuthenticationError
    from app.api.deps import get_actor as real_get_actor
    from app.api import deps as api_deps

    def override_get_db() -> Iterator[Session]:
        yield db

    def _override_get_actor(request: Request):
        """Test-only actor resolution.

        Accepts the real FastAPI Request (not a query parameter). Legacy
        X-Actor-Id mapping is supported only inside tests to preserve Phase 2A
        regression coverage while production auth remains session-based.
        """
        session = db  # use the per-test session from fixture closure
        legacy = request.headers.get("X-Actor-Id")
        if legacy:
            actor = _legacy_actor_for_header(session, legacy)
            if actor is not None:
                # Preserve legacy actor id strings in tests so Phase 2A regression
                # assertions on recorded actor identifiers remain meaningful.
                if actor.actor_id != legacy:
                    from dataclasses import replace
                    actor = replace(actor, actor_id=legacy)
                return actor
            raise AuthenticationError("Unknown legacy test actor.", details={"reason": "unknown_actor"})
        token, transport = api_deps._session_token(request)
        if token is None:
            raise AuthenticationError("Authentication required.", details={"reason": "session_required"})
        record = api_deps.find_by_access_token(session, token)
        if record is None:
            raise AuthenticationError("Your session is no longer valid.", details={"reason": "session_unknown"})
        # Production rejects revoked and expired sessions before anything else;
        # the harness must not be more permissive than the real dependency.
        if record.revoked_at is not None:
            raise AuthenticationError("Your session has been revoked.", details={"reason": "session_revoked"})
        if not api_deps.access_is_valid(record):
            raise AuthenticationError("Your session has expired.", details={"reason": "session_expired"})
        from app.db.models.identity import User
        if transport == "cookie":
            api_deps._check_csrf(request, record)
        user = session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("This account is not active.", details={"reason": "account_inactive"})
        from app.core.actors import active_memberships, build_principal, utcnow
        from app.core.sessions import as_utc
        memberships = active_memberships(session, user.id)
        membership_ids = {row.organization_id for row in memberships}
        active = record.organization_id if record.organization_id in membership_ids else None
        principal = build_principal(
            session, user=user, auth_session=record,
            membership=next((row for row in memberships if row.organization_id == active), None) if active else None,
            memberships=memberships,
        )
        last_seen = as_utc(record.last_seen_at)
        if last_seen is None or (utcnow() - last_seen).total_seconds() > 60:
            record.last_seen_at = utcnow()
            session.commit()
        # Mirror the production dependency so the forced-rotation rule is
        # exercised by the same path the application uses.
        api_deps.enforce_password_rotation(request, principal)
        return principal

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[real_get_actor] = _override_get_actor
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()



# --- factories -------------------------------------------------------------


def make_organization(db: Session, **overrides) -> Organization:
    suffix = uuid.uuid4().hex[:8]
    values = {
        "name": f"Test Organization {suffix}",
        "slug": f"test-org-{suffix}",
        "sector": OrganizationSector.CHEMICALS,
        "country": "Netherlands",
        "city": "Rotterdam",
        "latitude": 51.92,
        "longitude": 4.47,
        "is_demo": False,
        "data_source": DataSource.FORM,
    }
    values.update(overrides)
    organization = Organization(**values)
    db.add(organization)
    db.flush()
    return organization


def make_material(db: Session, organization: Organization, **overrides) -> Material:
    values = {
        "organization_id": organization.id,
        "reference_code": f"LM-{uuid.uuid4().hex[:8].upper()}",
        "name": "Test material stream",
        "category": MaterialCategory.METALS,
        "quantity_available": 100.0,
        "unit": MaterialUnit.TONNE,
        "condition": MaterialCondition.AS_GENERATED,
        "status": MaterialStatus.AVAILABLE,
        "hazard_class": "non_hazardous",
        "availability_start": TODAY - timedelta(days=10),
        "availability_end": TODAY + timedelta(days=90),
        "data_source": DataSource.FORM,
        "is_demo": False,
    }
    values.update(overrides)
    material = Material(**values)
    db.add(material)
    db.flush()
    return material


def add_specification(
    db: Session,
    material: Material,
    *,
    purity: float | None = 95.0,
    contamination: float | None = 0.5,
    moisture: float | None = 1.0,
) -> MaterialSpecification:
    specification = MaterialSpecification(
        material_id=material.id,
        purity_pct=purity,
        contamination_pct=contamination,
        moisture_pct=moisture,
        composition=[],
        contaminants={},
    )
    db.add(specification)
    db.flush()
    material.specification = specification
    return specification


def make_demand(db: Session, organization: Organization, **overrides) -> ResourceDemand:
    values = {
        "organization_id": organization.id,
        "title": f"Test demand {uuid.uuid4().hex[:6]}",
        "category": MaterialCategory.METALS,
        "min_quantity": 10.0,
        "max_quantity": 500.0,
        "unit": MaterialUnit.TONNE,
        "frequency": DemandFrequency.CONTINUOUS,
        "min_purity_pct": None,
        "max_contamination_pct": None,
        "max_moisture_pct": None,
        "prohibited_hazards": [],
        "max_distance_km": 500.0,
        "needed_from": TODAY,
        "needed_until": TODAY + timedelta(days=180),
        "currency": "EUR",
        "status": DemandStatus.OPEN,
        "data_source": DataSource.FORM,
        "is_demo": False,
    }
    values.update(overrides)
    demand = ResourceDemand(**values)
    db.add(demand)
    db.flush()
    return demand


def make_opportunity(
    db: Session,
    material: Material,
    demand: ResourceDemand,
    supplier: Organization,
    consumer: Organization,
    **overrides,
) -> RecoveryOpportunity:
    values = {
        "material_id": material.id,
        "resource_demand_id": demand.id,
        "supplier_organization_id": supplier.id,
        "consumer_organization_id": consumer.id,
        "compatibility_status": CompatibilityStatus.COMPATIBLE,
        "compatibility_score": 92,
        "compatibility_rules": [],
        "score_breakdown": {},
        "match_quantity": 100.0,
        "unit": MaterialUnit.TONNE,
        "distance_km": 42.0,
        "transport_required": True,
        "status": OpportunityStatus.IDENTIFIED,
        "discovery_method": "deterministic_rule_match",
        "is_demo": False,
    }
    values.update(overrides)
    opportunity = RecoveryOpportunity(**values)
    db.add(opportunity)
    db.flush()
    return opportunity


def make_proposal(
    db: Session,
    opportunity: RecoveryOpportunity,
    *,
    quantity: float = 100.0,
    status: ProposalStatus = ProposalStatus.DRAFT,
    **overrides,
) -> RecoveryProposal:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    values = {
        "opportunity_id": opportunity.id,
        "proposed_by_organization_id": opportunity.supplier_organization_id,
        "receiving_organization_id": opportunity.consumer_organization_id,
        "quantity": quantity,
        "unit": opportunity.unit,
        "price_per_unit": 20.0,
        "currency": "EUR",
        "status": status,
        "compatibility_status": opportunity.compatibility_status,
        "terms": {},
        "is_demo": False,
        "version": 0,
    }
    values.update(overrides)

    # Fill the evidence the lifecycle CHECK constraints require for each state so
    # factories can build records in any state without weakening the schema.
    if status != ProposalStatus.DRAFT:
        values.setdefault("submitted_at", now)
        values.setdefault("submitted_by", "test-coordinator")
    if status in {
        ProposalStatus.APPROVED,
        ProposalStatus.IN_PROGRESS,
        ProposalStatus.COMPLETED,
    }:
        values.setdefault("approved_at", now)
        values.setdefault("approved_by", "test-approver")
        values.setdefault("approval_reference", "TEST-APPR-0001")
    if status in {ProposalStatus.IN_PROGRESS, ProposalStatus.COMPLETED}:
        values.setdefault("started_at", now)
    if status == ProposalStatus.COMPLETED:
        values.setdefault("completed_at", now)
    if status == ProposalStatus.REJECTED:
        values.setdefault("rejected_at", now)
        values.setdefault("rejected_by", "test-reviewer")
        values.setdefault("rejection_reason", "Test rejection reason")
    if status == ProposalStatus.WITHDRAWN:
        values.setdefault("withdrawn_at", now)
        values.setdefault("withdrawn_by", "test-coordinator")
    if status == ProposalStatus.CANCELLED:
        values.setdefault("cancelled_at", now)
        values.setdefault("cancellation_reason", "Test cancellation reason")
    if status == ProposalStatus.FAILED:
        values.setdefault("failed_at", now)
        values.setdefault("failure_reason", "Test failure reason")

    proposal = RecoveryProposal(**values)
    db.add(proposal)
    db.flush()
    return proposal


def make_transaction(
    db: Session,
    proposal: RecoveryProposal,
    *,
    status: TransactionStatus = TransactionStatus.CREATED,
    verified_quantity: float | None = None,
    **overrides,
) -> RecoveryTransaction:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    values = {
        "proposal": proposal,
        "proposal_id": proposal.id,
        "status": status,
        "source_organization_id": proposal.proposed_by_organization_id,
        "destination_organization_id": proposal.receiving_organization_id,
        "accepted_quantity": proposal.quantity,
        "verified_quantity": verified_quantity,
        "unit": proposal.unit,
        "transport_distance_km": 42.0,
        "carrier_name": "Test Carrier",
        "verified_at": now if verified_quantity is not None else None,
        "verification_method": (
            VerificationMethod.WEIGHBRIDGE_TICKET if verified_quantity is not None else None
        ),
        "verified_by": "test-auditor" if verified_quantity is not None else None,
        "evidence": {},
        "is_demo": False,
        "version": 0,
    }
    values.update(overrides)

    if status in {
        TransactionStatus.TRANSFERRED,
        TransactionStatus.VERIFIED,
    }:
        values.setdefault("transferred_quantity", proposal.quantity)
        values.setdefault("transferred_at", now)
        values.setdefault("transfer_recorded_by", "test-coordinator")
        values.setdefault("transfer_reference", "TEST-WB-0001")
        values.setdefault("material_identification", "TEST-MATERIAL-BATCH")
    if status == TransactionStatus.REJECTED:
        values.setdefault("rejected_at", now)
        values.setdefault("rejected_by", "test-auditor")
        values.setdefault("rejection_reason", "Test rejection reason")
    if status == TransactionStatus.CANCELLED:
        values.setdefault("cancelled_at", now)
        values.setdefault("cancelled_by", "test-coordinator")
        values.setdefault("cancellation_reason", "Test cancellation reason")

    transaction = RecoveryTransaction(**values)
    db.add(transaction)
    db.flush()
    return transaction


# --- auth helpers (Phase 2B) ----------------------------------------------

from app.core.security import hash_password
from app.core.sessions import issue_session, utcnow
from app.db.enums import MembershipRole, MembershipScope, MembershipStatus
from app.db.models.identity import OrganizationMembership, User


def make_user(
    db: Session,
    *,
    email: str | None = None,
    full_name: str = "Test User",
    password: str = "StrongPass!2345",
    is_active: bool = True,
    is_platform_admin: bool = False,
) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=(email or f"user-{suffix}@example.com").lower(),
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=is_active,
        is_platform_admin=is_platform_admin,
        # Fixtures represent accounts whose owner already holds their password;
        # otherwise every test user would be forced through rotation.
        password_changed_at=utcnow(),
    )
    db.add(user)
    db.flush()
    return user


def make_membership(
    db: Session,
    user: User,
    organization: Organization,
    *,
    role: MembershipRole = MembershipRole.COORDINATOR,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    scope: MembershipScope = MembershipScope.ORGANIZATION,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=organization.id,
        role=role,
        status=status,
        scope=scope,
        accepted_at=None,
    )
    db.add(membership)
    db.flush()
    return membership


def login_client(
    client: TestClient,
    db: Session,
    user: User,
    organization_id=None,
    *,
    mfa_verified: bool = True,
) -> dict[str, str]:
    """Create a session for user and set auth cookies on the TestClient.

    Batch 12 platform routes require a session that has proved a second factor.
    Platform-focused suites treat a directly issued test session as already
    verified; MFA tests pass ``mfa_verified=False`` and exercise the gate itself.
    """
    memberships = db.scalars(
        __import__("sqlalchemy").select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
    ).all()
    org_id = organization_id or (memberships[0].organization_id if memberships else None)
    record, bundle = issue_session(db, user, organization_id=org_id)
    if mfa_verified:
        record.mfa_verified_at = record.created_at
        record.mfa_method = "totp"
    db.commit()
    client.cookies.set("lm_session", bundle.access_token)
    client.cookies.set("lm_refresh", bundle.refresh_token)
    client.cookies.set("lm_csrf", bundle.csrf_token)
    return {"X-CSRF-Token": bundle.csrf_token}


def auth_headers_for(
    client: TestClient,
    db: Session,
    *,
    role: str = "admin",
    organization: Organization | None = None,
    supplier: Organization | None = None,
    consumer: Organization | None = None,
) -> dict[str, str]:
    """Provision and authenticate a canonical test actor.

    Roles: admin, coordinator, reviewer, approver, auditor, viewer.
    coordinator is scoped to supplier if provided; reviewer/approver/auditor/viewer
    are scoped to consumer by default in lifecycle-style tests.
    """
    role = role.lower()
    if role in {"admin", "platform_admin"}:
        user = make_user(db, full_name="Platform Admin", is_platform_admin=True)
        return login_client(client, db, user, organization.id if organization else None)

    role_map = {
        "coordinator": MembershipRole.COORDINATOR,
        "reviewer": MembershipRole.REVIEWER,
        "approver": MembershipRole.APPROVER,
        "auditor": MembershipRole.AUDITOR,
        "viewer": MembershipRole.VIEWER,
        "org_admin": MembershipRole.ORG_ADMIN,
    }
    mrole = role_map.get(role, MembershipRole.VIEWER)
    org = organization
    if org is None:
        if role == "coordinator":
            org = supplier
        else:
            org = consumer or supplier
    if org is None:
        raise ValueError("organization required for non-admin test actors")
    user = make_user(db, full_name=f"Test {role.title()}")
    make_membership(db, user, org, role=mrole)
    return login_client(client, db, user, org.id)


class ActorHeaders(dict):
    """Compatibility wrapper: acts like headers dict but can carry auth setup info."""
    pass
