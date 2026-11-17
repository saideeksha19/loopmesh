"""Provision the initial platform administrator.

This command is intentionally local-only: it must be executed by an operator with
access to the application environment and database. It never creates an account
automatically, never accepts a password on the command line, and never prints
credentials or tokens.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/provision_admin.py --email admin@example.com --name "Admin User"
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

# Ensure `app` is importable when run as a script from backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision the initial LOOPMESH platform administrator.")
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--name", required=True, help="Administrator full name")
    args = parser.parse_args(argv)

    # Refuse obvious non-interactive foot-guns: require a TTY for password entry.
    if not sys.stdin.isatty():
        print("Refusing to read a password from a non-interactive stdin.", file=sys.stderr)
        return 2

    password = getpass.getpass("New administrator password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 2

    # Local imports after path/bootstrap checks so misconfiguration fails clearly.
    from sqlalchemy import select

    from app.core.security import hash_password, normalise_email, validate_password_strength
    from app.core.sessions import utcnow
    from app.db.models.identity import User
    from app.db.session import SessionLocal

    try:
        validate_password_strength(password)
    except Exception as exc:  # noqa: BLE001 - show policy message to operator
        print(f"Password rejected: {getattr(exc, 'message', str(exc))}", file=sys.stderr)
        return 2

    email = normalise_email(args.email)
    full_name = " ".join(args.name.split()).strip()
    if len(full_name) < 2:
        print("A full name is required.", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        existing = session.scalar(select(User.id).limit(1))
        if existing is not None:
            print("Provisioning refused: a user already exists.", file=sys.stderr)
            return 1

        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            is_active=True,
            is_platform_admin=True,
        )
        session.add(user)
        session.commit()

    print(f"Platform administrator provisioned for {email}.")
    print("Sign in through the application. No credentials or tokens were printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
