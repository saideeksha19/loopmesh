"""Seed a disposable SQLite database for Playwright browser tests.

The database is created by Alembic migrations at the requested URL, then seeded
with two synthetic platform operators and one organisation.  No demo database
is touched; the caller must point DATABASE_URL at a throwaway file.

Environment variables read:
  E2E_DATABASE_URL   SQLite URL (e.g. sqlite:///./tmp/e2e_browser.db)
  E2E_MFA_KEY        Fernet key (required for MFA enrolment tests)
  E2E_RESET          "1" to delete the database file first
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    raw = url.removeprefix("sqlite:///")
    if raw.startswith("/"):
        # sqlite:////abs/path -> /abs/path
        if url.startswith("sqlite:////"):
            return Path(url.removeprefix("sqlite:///"))
        return Path(raw)
    return (BACKEND / raw).resolve()


def main() -> int:
    database_url = os.environ.get("E2E_DATABASE_URL", "").strip()
    mfa_key = os.environ.get("E2E_MFA_KEY", "").strip()
    if not database_url:
        print("E2E_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not mfa_key:
        print("E2E_MFA_KEY is required", file=sys.stderr)
        return 2

    db_path = _sqlite_path(database_url)
    if os.environ.get("E2E_RESET") == "1" and db_path and db_path.exists():
        db_path.unlink()

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["ENVIRONMENT"] = "test"
    env["MFA_ENCRYPTION_KEY"] = mfa_key
    env.setdefault("CORS_ORIGINS", "http://127.0.0.1:3100,http://localhost:3100")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode

    # Seed after migrations so ORM models include Batch 13 columns.
    os.environ.update(
        {
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "test",
            "MFA_ENCRYPTION_KEY": mfa_key,
        }
    )
    from app.core.config import settings
    from app.core.security import hash_password
    from app.db.enums import OrganizationSector, OrganizationStatus
    from app.db.models.identity import User
    from app.db.models.organization import Organization
    from app.db.session import SessionLocal
    from app.services import audit

    settings.database_url = database_url
    settings.environment = "test"
    settings.mfa_encryption_key = mfa_key

    with SessionLocal() as session:
        if session.query(User).filter(User.email == "e2e-requester@example.com").first():
            print("E2E database already seeded")
            return 0

        org = Organization(
            name="E2E Tenant Org",
            slug="e2e-tenant-org",
            sector=OrganizationSector.CHEMICALS,
            country="Netherlands",
            city="Rotterdam",
            status=OrganizationStatus.ACTIVE,
            is_demo=False,
        )
        session.add(org)
        session.flush()

        for email, name in (
            ("e2e-requester@example.com", "E2E Requester"),
            ("e2e-approver@example.com", "E2E Approver"),
            ("e2e-viewer@example.com", "E2E Viewer"),
        ):
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password("StrongPass!2345"),
                is_active=True,
                is_platform_admin=True,
                password_changed_at=__import__("app.core.sessions", fromlist=["utcnow"]).utcnow(),
            )
            session.add(user)
            session.flush()
            # Viewer gets read-only platform permissions in a real deployment via
            # role assignment; the platform console gates on capabilities. For the
            # seeded synthetic operators we keep them as platform admins but tests
            # exercise the UI/API capability checks through routes.
            audit.record_event(
                session,
                event_type="test.e2e_seeded",
                entity_type="user",
                entity_id=user.id,
                actor="e2e-seed",
                summary=f"Seeded synthetic E2E operator {email}.",
                payload={"synthetic": True},
            )

        # A non-platform member for direct-URL/permission filtering checks.
        tenant_user = User(
            email="e2e-member@example.com",
            full_name="E2E Member",
            password_hash=hash_password("StrongPass!2345"),
            is_active=True,
            is_platform_admin=False,
            password_changed_at=__import__("app.core.sessions", fromlist=["utcnow"]).utcnow(),
        )
        session.add(tenant_user)
        session.flush()
        from app.db.enums import MembershipRole, MembershipScope, MembershipStatus
        from app.db.models.identity import OrganizationMembership

        session.add(
            OrganizationMembership(
                user_id=tenant_user.id,
                organization_id=org.id,
                role=MembershipRole.VIEWER,
                scope=MembershipScope.ORGANIZATION,
                status=MembershipStatus.ACTIVE,
            )
        )

        audit.record_event(
            session,
            event_type="organization.created",
            entity_type="organization",
            entity_id=org.id,
            actor="e2e-seed",
            organization_id=org.id,
            summary="Seeded synthetic E2E organisation.",
            payload={"synthetic": True},
        )
        session.commit()

    print(
        json.dumps(
            {
                "database_url": database_url,
                "requester": "e2e-requester@example.com",
                "approver": "e2e-approver@example.com",
                "viewer": "e2e-viewer@example.com",
                "member": "e2e-member@example.com",
                "password": "StrongPass!2345",
                "organization_slug": "e2e-tenant-org",
            }
        )
    )
    return 0


if __name__ == "__main__":
    import json

    raise SystemExit(main())
