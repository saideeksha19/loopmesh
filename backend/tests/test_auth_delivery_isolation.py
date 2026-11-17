"""Environment isolation for the development delivery-token adapter.

``POST /auth/invitations`` and ``POST /auth/forgot-password`` can return the raw
token so a developer can finish the flow locally without an email transport.
That convenience is a live credential, so it must be restricted to an explicit
allow-list of local environments and fail closed everywhere else.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_token
from app.db.enums import MembershipRole
from app.db.models.identity import Invitation, PasswordResetToken
from tests.conftest import login_client, make_membership, make_organization, make_user

API = "/api/v1/auth"

ALLOWED_ENVIRONMENTS = ("development", "test")
BLOCKED_ENVIRONMENTS = ("staging", "production", "not-a-real-environment")


@pytest.fixture()
def inviter(client, db):
    """A platform admin signed in to a throwaway organisation."""
    org = make_organization(db, name="Delivery Isolation Org", slug="delivery-isolation")
    admin = make_user(db, email="delivery-admin@example.com", is_platform_admin=True)
    make_membership(db, admin, org, role=MembershipRole.ORG_ADMIN)
    csrf = login_client(client, db, admin, organization_id=org.id)
    return org, csrf


def _create_invitation(client, org, csrf, email: str):
    return client.post(
        f"{API}/invitations",
        json={
            "email": email,
            "organization_id": str(org.id),
            "role": "viewer",
            "scope": "organization",
        },
        headers=csrf,
    )


def _request_reset(client, email: str):
    return client.post(f"{API}/forgot-password", json={"email": email})


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
def test_allowed_environments_still_receive_invitation_token(
    client, db, inviter, monkeypatch, environment
):
    org, csrf = inviter
    monkeypatch.setattr(settings, "environment", environment)

    res = _create_invitation(client, org, csrf, f"{environment}-invite@example.com")
    assert res.status_code == 201, res.text
    token = res.json()["delivery_token"]
    assert token

    # The returned value must be the real token, not a placeholder.
    stored = db.scalar(select(Invitation).where(Invitation.email == f"{environment}-invite@example.com"))
    assert stored is not None
    assert stored.token_hash == hash_token(token)


@pytest.mark.parametrize("environment", ALLOWED_ENVIRONMENTS)
def test_allowed_environments_still_receive_reset_token(client, db, monkeypatch, environment):
    user = make_user(db, email=f"{environment}-reset@example.com")
    db.commit()
    monkeypatch.setattr(settings, "environment", environment)

    res = _request_reset(client, user.email)
    assert res.status_code == 200, res.text
    token = res.json()["delivery_token"]
    assert token

    stored = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert stored is not None
    assert stored.token_hash == hash_token(token)


@pytest.mark.parametrize("environment", BLOCKED_ENVIRONMENTS)
def test_blocked_environments_never_receive_invitation_token(
    client, db, inviter, monkeypatch, environment
):
    org, csrf = inviter
    monkeypatch.setattr(settings, "environment", environment)

    email = f"{environment}-blocked@example.com"
    res = _create_invitation(client, org, csrf, email)
    # The invitation itself is still created: only the token is withheld.
    assert res.status_code == 201, res.text
    assert res.json()["delivery_token"] is None

    stored = db.scalar(select(Invitation).where(Invitation.email == email))
    assert stored is not None
    assert stored.token_hash


@pytest.mark.parametrize("environment", BLOCKED_ENVIRONMENTS)
def test_blocked_environments_never_receive_reset_token(client, db, monkeypatch, environment):
    user = make_user(db, email=f"{environment}-reset-blocked@example.com")
    db.commit()
    monkeypatch.setattr(settings, "environment", environment)

    res = _request_reset(client, user.email)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["delivery_token"] is None
    # Non-enumerating message and unchanged delivery semantics.
    assert body["message"] == _request_reset(client, "unknown-account@example.com").json()["message"]

    stored = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert stored is not None
    assert stored.token_hash
