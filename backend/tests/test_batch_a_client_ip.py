"""Batch A: trusted proxy resolution and rate-limit client identity.

Covers R1 (client IP / bucket collapse) and R5 (explicit proxy trust).
"""

from __future__ import annotations

import pytest
from fastapi import Request

from app.core import security_limiter
from app.core.config import settings
from app.core.rate_limit import client_key
from app.core.security import resolve_client_ip
from tests.conftest import make_user

API = "/api/v1/auth"


def _request(
    peer: str | None = "198.51.100.10",
    xff: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345) if peer is not None else None,
    }
    return Request(scope)


# --- explicit trusted-proxy configuration ---------------------------------


def test_proxy_header_trust_is_disabled_by_default():
    req = _request(peer="10.0.0.1", xff="203.0.113.9")
    assert resolve_client_ip(req) == "10.0.0.1"


def test_production_rejects_wildcard_trusted_proxies():
    for wildcard in ("*", "0.0.0.0/0", "::/0"):
        with pytest.raises(RuntimeError, match="wildcards are not allowed"):
            settings.__class__(
                environment="production",
                debug=False,
                database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
                cors_origins="https://app.example.com",
                trust_proxy_headers=True,
                trusted_proxy_ips=f"127.0.0.1,{wildcard}",
            ).validate_runtime_security()


def test_production_rejects_enabled_trust_without_proxies():
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_IPS must be configured"):
        settings.__class__(
            environment="production",
            debug=False,
            database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
            cors_origins="https://app.example.com",
            trust_proxy_headers=True,
            trusted_proxy_ips="",
        ).validate_runtime_security()


# --- safe X-Forwarded-For resolution ---------------------------------------


def test_spoofed_xff_ignored_when_trust_disabled():
    req = _request(peer="198.51.100.10", xff="203.0.113.1, 203.0.113.2")
    assert (
        resolve_client_ip(req, trust_proxy_headers=False, trusted_proxy_ips=[])
        == "198.51.100.10"
    )


def test_spoofed_xff_ignored_from_untrusted_peer():
    req = _request(peer="198.51.100.10", xff="203.0.113.1")
    resolved = resolve_client_ip(
        req,
        trust_proxy_headers=True,
        trusted_proxy_ips=["127.0.0.1", "10.0.0.0/8"],
    )
    assert resolved == "198.51.100.10"


def test_right_to_left_resolution_uses_first_untrusted_hop():
    req = _request(peer="10.0.0.2", xff="203.0.113.9, 10.0.0.1")
    resolved = resolve_client_ip(
        req,
        trust_proxy_headers=True,
        trusted_proxy_ips=["10.0.0.0/8"],
    )
    assert resolved == "203.0.113.9"


def test_right_to_left_skips_multiple_trusted_hops():
    req = _request(peer="10.0.0.3", xff="198.51.100.7, 10.0.0.1, 10.0.0.2")
    resolved = resolve_client_ip(
        req,
        trust_proxy_headers=True,
        trusted_proxy_ips=["10.0.0.0/8"],
    )
    assert resolved == "198.51.100.7"


def test_all_trusted_hops_falls_back_to_leftmost():
    req = _request(peer="10.0.0.3", xff="10.0.0.1, 10.0.0.2")
    resolved = resolve_client_ip(
        req,
        trust_proxy_headers=True,
        trusted_proxy_ips=["10.0.0.0/8"],
    )
    assert resolved == "10.0.0.1"


def test_no_forwarded_header_from_trusted_peer_returns_peer():
    req = _request(peer="10.0.0.2", xff=None)
    resolved = resolve_client_ip(
        req,
        trust_proxy_headers=True,
        trusted_proxy_ips=["10.0.0.0/8"],
    )
    assert resolved == "10.0.0.2"


# --- rate-limit and session identification use the resolver ----------------


def test_client_keys_distinguish_clients_via_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.0/8")
    a = client_key(_request(peer="10.0.0.2", xff="203.0.113.1"), scope="login")
    b = client_key(_request(peer="10.0.0.2", xff="203.0.113.2"), scope="login")
    spoofed = client_key(_request(peer="198.51.100.50", xff="203.0.113.1"), scope="login")
    assert a != b
    assert spoofed != a
    assert spoofed == client_key(_request(peer="198.51.100.50", xff="9.9.9.9"), scope="login")


def test_multiple_clients_get_independent_buckets(db, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.0/8")
    req_a = _request(peer="10.0.0.2", xff="203.0.113.1")
    req_b = _request(peer="10.0.0.2", xff="203.0.113.2")
    limit = 2
    for _ in range(limit):
        security_limiter.hit(
            db,
            key=client_key(req_a, scope="login"),
            limit=limit,
            window_seconds=3600,
        )
    with pytest.raises(Exception):
        security_limiter.hit(
            db,
            key=client_key(req_a, scope="login"),
            limit=limit,
            window_seconds=3600,
        )
    security_limiter.hit(
        db,
        key=client_key(req_b, scope="login"),
        limit=limit,
        window_seconds=3600,
    )


def test_password_reset_confirm_bucket_is_not_global(client):
    original = settings.auth_reset_attempts_per_hour
    settings.auth_reset_attempts_per_hour = 2
    try:
        token_a = "token-a-" + "x" * 40
        token_b = "token-b-" + "y" * 40
        for _ in range(2):
            res = client.post(
                f"{API}/reset-password",
                json={"token": token_a, "new_password": "AnotherStrong!2345"},
            )
            assert res.status_code in {400, 401}, res.text
        blocked = client.post(
            f"{API}/reset-password",
            json={"token": token_a, "new_password": "AnotherStrong!2345"},
        )
        assert blocked.status_code == 429

        other = client.post(
            f"{API}/reset-password",
            json={"token": token_b, "new_password": "AnotherStrong!2345"},
        )
        assert other.status_code in {400, 401}, other.text
        assert other.status_code != 429
    finally:
        settings.auth_reset_attempts_per_hour = original


def test_aggregate_login_limit_blocks_one_client_across_accounts(client, db, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_attempts_per_hour", 3)
    emails = [
        "agg-a@example.com",
        "agg-b@example.com",
        "agg-c@example.com",
        "agg-d@example.com",
    ]
    for email in emails:
        make_user(db, email=email)
    db.commit()

    statuses = []
    for email in emails:
        res = client.post(
            f"{API}/login",
            json={"email": email, "password": "WrongPassword!2345"},
        )
        statuses.append(res.status_code)

    assert 429 in statuses
    assert statuses.index(429) <= 3


def test_rotating_xff_does_not_create_new_buckets_when_untrusted(client, db, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_attempts_per_hour", 3)
    make_user(db, email="xff-rotate@example.com")
    db.commit()
    res = None
    for i in range(5):
        res = client.post(
            f"{API}/login",
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
            json={"email": "xff-rotate@example.com", "password": "WrongPassword!2345"},
        )
    assert res is not None and res.status_code == 429
