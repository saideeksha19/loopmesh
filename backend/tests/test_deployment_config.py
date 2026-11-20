"""Deployment configuration: provider database URLs and tenant bootstrapping.

These cover the two failure modes that only appear once the application runs on
a managed platform:

* a hosting provider issues ``postgresql://…``, which SQLAlchemy would otherwise
  route to psycopg2 (not installed here);
* a migrated database has no organisation, so the first administrator cannot be
  created through the UI and must be provisioned by an operator.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.db.enums import MembershipRole, MembershipStatus, OrganizationSector
from app.db.models.identity import OrganizationMembership, User
from app.db.models.organization import Organization

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provision_tenant.py"
_spec = importlib.util.spec_from_file_location("loopmesh_provision_tenant", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
provision_tenant = importlib.util.module_from_spec(_spec)
# Register before execution so dataclasses can resolve the defining module.
sys.modules[_spec.name] = provision_tenant
_spec.loader.exec_module(provision_tenant)


# --- database URL normalisation -------------------------------------------


def test_provider_postgresql_url_selects_psycopg3() -> None:
    settings = Settings(database_url="postgresql://user:pass@db.internal:5432/loopmesh")
    assert settings.database_url == "postgresql+psycopg://user:pass@db.internal:5432/loopmesh"


def test_legacy_postgres_scheme_is_normalised() -> None:
    settings = Settings(database_url="postgres://user:pass@db.internal:5432/loopmesh")
    assert settings.database_url == "postgresql+psycopg://user:pass@db.internal:5432/loopmesh"


def test_query_parameters_survive_normalisation() -> None:
    settings = Settings(
        database_url="postgresql://user:pass@db.internal:5432/loopmesh?sslmode=require"
    )
    assert settings.database_url == (
        "postgresql+psycopg://user:pass@db.internal:5432/loopmesh?sslmode=require"
    )


def test_explicit_driver_is_preserved() -> None:
    url = "postgresql+psycopg://user:pass@db.internal:5432/loopmesh"
    assert Settings(database_url=url).database_url == url


def test_sqlite_is_preserved() -> None:
    assert Settings(database_url="sqlite://").database_url == "sqlite://"


def test_unsupported_driver_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://user:pass@db.internal:3306/loopmesh")


def test_production_accepts_a_normalised_provider_url() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql://user:pass@db.internal:5432/loopmesh",
        cors_origins="https://app.example.com",
        allowed_hosts="app.example.com,loopmesh-api",
        debug=False,
    )
    # Must not raise: the provider URL was rewritten to the installed driver.
    settings.validate_runtime_security()
    assert not settings.is_sqlite


def test_production_still_refuses_sqlite() -> None:
    settings = Settings(
        environment="production",
        database_url="sqlite:///loopmesh_dev.db",
        cors_origins="https://app.example.com",
        allowed_hosts="app.example.com",
    )
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        settings.validate_runtime_security()


# --- tenant provisioning ---------------------------------------------------


def _provision(db: Session, **overrides):
    values = {
        "email": "Admin@Example.com",
        "full_name": "Ada  Admin",
        "organization_name": "Acme  Recovery",
        "slug": "acme-recovery",
        "sector": OrganizationSector.STEEL_METALS,
        "country": "IN",
        "password": "CorrectHorse9!",
    }
    values.update(overrides)
    return provision_tenant.provision(db, **values)


def test_provision_creates_organisation_administrator_and_membership(db: Session) -> None:
    result = _provision(db)
    db.commit()

    assert result.organization_created
    assert result.user_created
    assert result.membership_created
    assert result.platform_admin_granted

    user = db.scalar(select(User))
    organization = db.scalar(select(Organization))
    membership = db.scalar(select(OrganizationMembership))

    assert user is not None and user.email == "admin@example.com"
    assert user.full_name == "Ada Admin"  # whitespace collapsed
    assert user.is_platform_admin
    assert user.password_hash and not user.password_hash.startswith("CorrectHorse")
    assert organization is not None and organization.slug == "acme-recovery"
    assert organization.country == "IN"
    assert membership is not None
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.role is MembershipRole.ORG_ADMIN
    assert membership.accepted_at is not None


def test_provision_is_idempotent(db: Session) -> None:
    _provision(db)
    db.commit()

    # No password on a re-run: the account already exists.
    again = _provision(db, password=None)
    db.commit()

    assert not again.organization_created
    assert not again.user_created
    assert not again.membership_created
    assert not again.platform_admin_granted

    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Organization)) == 1
    assert db.scalar(select(func.count()).select_from(OrganizationMembership)) == 1


def test_provision_corrects_an_existing_membership_role(db: Session) -> None:
    _provision(db)
    db.commit()

    changed = _provision(db, password=None, role=MembershipRole.AUDITOR)
    db.commit()

    assert changed.membership_role_changed
    assert not changed.membership_created
    assert db.scalar(select(func.count()).select_from(OrganizationMembership)) == 1
    assert db.scalar(select(OrganizationMembership)).role is MembershipRole.AUDITOR


def test_provision_requires_a_country_for_a_new_organisation(db: Session) -> None:
    with pytest.raises(provision_tenant.ProvisioningError, match="country"):
        _provision(db, country=None)

    # Nothing was written, not even the user that was resolved first.
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert db.scalar(select(func.count()).select_from(Organization)) == 0


def test_provision_rejects_a_password_below_policy(db: Session) -> None:
    with pytest.raises(AppError):
        _provision(db, password="short")

    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_provision_rejects_an_invalid_slug(db: Session) -> None:
    with pytest.raises(provision_tenant.ProvisioningError):
        _provision(db, slug="Acme Recovery!")
