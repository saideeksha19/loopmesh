"""Provision the first organisation and its administrator (idempotent).

A fresh production database has no tenant, so nobody can sign in until one
exists: login resolves an active membership, and memberships require both a
user and an organisation. This command creates that minimum in one transaction:

* the organisation (matched by slug, so re-runs reuse it),
* the administrator user (matched by email, so re-runs reuse it),
* their active membership, and optionally platform-administrator rights.

It is safe to run repeatedly: existing rows are reused, a membership is created
or corrected instead of duplicated, and nothing is ever deleted. A password is
only requested when the user does not exist yet, and it is read from a TTY with
``getpass`` -- never from the command line, an environment variable or a file.
No password, token or hash is printed.

Because the password prompt needs a terminal, run this from an interactive
shell (Render service shell, an SSH session or a local terminal), not from a
build/deploy hook.

Usage (from backend/):
    python scripts/provision_tenant.py \\
        --email admin@example.com --name "Ada Admin" \\
        --organization "Acme Recovery" --sector steel_metals --country IN

Add ``--dry-run`` to report what would change and roll it back.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure `app` is importable when run as a script from backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.exceptions import AppError  # noqa: E402
from app.core.security import (  # noqa: E402
    hash_password,
    normalise_email,
    validate_password_strength,
)
from app.core.sessions import utcnow  # noqa: E402
from app.db.enums import (  # noqa: E402
    DataSource,
    MembershipRole,
    MembershipScope,
    MembershipStatus,
    OrganizationSector,
    OrganizationStatus,
)
from app.db.models.identity import OrganizationMembership, User  # noqa: E402
from app.db.models.organization import Organization  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProvisioningError(Exception):
    """Operator input is incomplete or unsafe; nothing was written."""


@dataclass(slots=True)
class ProvisionResult:
    organization_id: str
    organization_created: bool
    user_id: str
    user_created: bool
    membership_created: bool
    membership_role_changed: bool
    platform_admin_granted: bool


def _stdin_is_interactive() -> bool:
    """True only for a real terminal.

    Windows reports character devices such as ``NUL`` (and some redirected
    pipes) as TTYs, so ``isatty()`` alone can pass while a password prompt
    would block forever. On Windows the stdin handle must also be a console.
    """
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    if os.name == "nt":
        try:
            import ctypes
            import msvcrt

            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        except (ImportError, OSError, ValueError):
            return False
        mode = ctypes.c_uint()
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    return True


def slugify(value: str, *, max_length: int = 80) -> str:
    """Derive a stable organisation slug from a display name."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:max_length].strip("-")


def provision(
    session: Session,
    *,
    email: str,
    full_name: str,
    organization_name: str,
    slug: str,
    sector: OrganizationSector,
    country: str | None,
    region: str | None = None,
    city: str | None = None,
    password: str | None = None,
    role: MembershipRole = MembershipRole.ORG_ADMIN,
    grant_platform_admin: bool = True,
) -> ProvisionResult:
    """Create the missing rows and return what changed.

    Only flushes; the caller owns the transaction so a dry run can roll back.
    """
    normalised_email = normalise_email(email)
    clean_name = " ".join(full_name.split())
    clean_org_name = " ".join(organization_name.split())
    clean_slug = slug.strip().lower()

    if "@" not in normalised_email or len(normalised_email) < 5:
        raise ProvisioningError("A valid email address is required.")
    if len(clean_name) < 2:
        raise ProvisioningError("A full name is required.")
    if len(clean_org_name) < 2:
        raise ProvisioningError("An organisation name is required.")
    if not SLUG_PATTERN.match(clean_slug) or len(clean_slug) > 80:
        raise ProvisioningError(
            "Organisation slug must be lowercase letters, digits and single hyphens."
        )

    # Resolve both rows and validate everything before writing anything, so a
    # refused run leaves no partial state behind.
    user = session.scalar(select(User).where(User.email == normalised_email))
    organization = session.scalar(select(Organization).where(Organization.slug == clean_slug))

    clean_country = (country or "").strip()
    if organization is None and not clean_country:
        raise ProvisioningError("A country is required when creating the organisation.")
    if user is None:
        if not password:
            raise ProvisioningError(
                "A password is required to create the administrator account."
            )
        validate_password_strength(password)

    user_created = False
    if user is None:
        user = User(
            email=normalised_email,
            full_name=clean_name,
            password_hash=hash_password(password),
            is_active=True,
            is_platform_admin=False,
        )
        session.add(user)
        session.flush()
        user_created = True

    organization_created = False
    if organization is None:
        organization = Organization(
            name=clean_org_name,
            slug=clean_slug,
            sector=sector,
            status=OrganizationStatus.ACTIVE,
            country=clean_country[:64],
            region=(region or "").strip()[:120] or None,
            city=(city or "").strip()[:120] or None,
            data_source=DataSource.FORM,
            is_demo=False,
        )
        session.add(organization)
        session.flush()
        organization_created = True

    membership = session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == organization.id,
        )
    )
    membership_created = False
    membership_role_changed = False
    if membership is None:
        # Acceptance is the creation moment. Supplying both explicitly keeps the
        # `accepted_at >= created_at` constraint true regardless of when the
        # database evaluates the column default.
        now = utcnow()
        membership = OrganizationMembership(
            user_id=user.id,
            organization_id=organization.id,
            role=role,
            status=MembershipStatus.ACTIVE,
            scope=MembershipScope.ORGANIZATION,
            created_at=now,
            accepted_at=now,
        )
        session.add(membership)
        membership_created = True
    else:
        # Re-running with a different role is an explicit operator correction;
        # it never duplicates the membership.
        if membership.role != role or membership.status != MembershipStatus.ACTIVE:
            membership.role = role
            membership.status = MembershipStatus.ACTIVE
            membership.accepted_at = (
                membership.accepted_at or membership.created_at or utcnow()
            )
            membership_role_changed = True

    platform_admin_granted = False
    if grant_platform_admin and not user.is_platform_admin:
        user.is_platform_admin = True
        platform_admin_granted = True

    session.flush()
    return ProvisionResult(
        organization_id=str(organization.id),
        organization_created=organization_created,
        user_id=str(user.id),
        user_created=user_created,
        membership_created=membership_created,
        membership_role_changed=membership_role_changed,
        platform_admin_granted=platform_admin_granted,
    )


def _report(
    result: ProvisionResult,
    *,
    dry_run: bool,
    email: str,
    slug: str,
    role: MembershipRole,
    grant_platform_admin: bool,
) -> None:
    verb = "would be" if dry_run else "was"
    if result.organization_created:
        print(f"Organisation {slug!r} {verb} created.")
    else:
        print(f"Organisation {slug!r} already exists; reused.")
    if result.user_created:
        print(f"Administrator {email} {verb} created.")
    else:
        print(f"User {email} already exists; reused.")
    if result.membership_created:
        print(f"Membership {verb} created with role {role.value}.")
    elif result.membership_role_changed:
        print("Existing membership was corrected to an active role.")
    else:
        print("Membership already active; unchanged.")
    if result.platform_admin_granted:
        granted_verb = "would be" if dry_run else "were"
        print(f"Platform administrator rights {granted_verb} granted.")
    elif grant_platform_admin:
        print("Platform administrator rights already present; unchanged.")
    else:
        print("Platform administrator rights left as they were (--no-platform-admin).")
    if dry_run:
        print("Dry run: no changes were committed.")
    else:
        print("Provisioning complete. No credentials or tokens were printed.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision the first LOOPMESH organisation and its administrator."
    )
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--name", required=True, help="Administrator full name")
    parser.add_argument("--organization", required=True, help="Organisation display name")
    parser.add_argument(
        "--slug",
        help="Organisation slug (default: derived from --organization)",
    )
    parser.add_argument(
        "--sector",
        required=True,
        choices=[member.value for member in OrganizationSector],
        help="Organisation sector",
    )
    parser.add_argument("--country", help="Country (required when creating the organisation)")
    parser.add_argument("--region", help="Optional region/state")
    parser.add_argument("--city", help="Optional city")
    parser.add_argument(
        "--role",
        default=MembershipRole.ORG_ADMIN.value,
        choices=[member.value for member in MembershipRole],
        help="Membership role inside the organisation (default: org_admin)",
    )
    parser.add_argument(
        "--no-platform-admin",
        dest="platform_admin",
        action="store_false",
        help="Do not grant platform-administrator rights",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the changes and roll them back",
    )
    args = parser.parse_args(argv)

    email = normalise_email(args.email)
    slug = args.slug or slugify(args.organization)
    if not SLUG_PATTERN.match(slug):
        print(
            "Organisation slug must be lowercase letters, digits and single hyphens.",
            file=sys.stderr,
        )
        return 2

    try:
        with SessionLocal() as session:
            password: str | None = None
            existing = session.scalar(select(User.id).where(User.email == email))
            if existing is None:
                # Only a new account needs a password, so re-runs stay usable
                # without a terminal.
                if not _stdin_is_interactive():
                    print(
                        "Refusing to read the initial password from a non-interactive stdin. "
                        "Run this from an interactive shell.",
                        file=sys.stderr,
                    )
                    return 2
                password = getpass.getpass("New administrator password: ")
                confirm = getpass.getpass("Confirm password: ")
                if password != confirm:
                    print("Passwords do not match.", file=sys.stderr)
                    return 2

            result = provision(
                session,
                email=email,
                full_name=args.name,
                organization_name=args.organization,
                slug=slug,
                sector=OrganizationSector(args.sector),
                country=args.country,
                region=args.region,
                city=args.city,
                password=password,
                role=MembershipRole(args.role),
                grant_platform_admin=args.platform_admin,
            )
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
    except ProvisioningError as exc:
        print(f"Provisioning refused: {exc}", file=sys.stderr)
        return 2
    except AppError as exc:  # password policy violation
        print(f"Password rejected: {getattr(exc, 'message', str(exc))}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(
            "Provisioning failed: the database rejected the change "
            f"({type(exc).__name__}). Check DATABASE_URL, migrations and logs.",
            file=sys.stderr,
        )
        return 1

    _report(
        result,
        dry_run=args.dry_run,
        email=email,
        slug=slug,
        role=MembershipRole(args.role),
        grant_platform_admin=args.platform_admin,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
