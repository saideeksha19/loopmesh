"""Password hashing, token generation and cookie helpers.

Everything sensitive in this module is generated with :mod:`secrets` and stored
only as a SHA-256 digest. Passwords use Argon2id with parameters from settings.

Rules enforced here:

* plaintext passwords never leave the caller,
* hashes are never returned to an HTTP response,
* token comparison is constant time,
* password policy is centralized so every entry point applies the same rules.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import ValidationError

# 32 bytes = 256 bits of entropy for session tokens, 48 for refresh tokens.
ACCESS_TOKEN_BYTES = 32
REFRESH_TOKEN_BYTES = 48
CSRF_TOKEN_BYTES = 24

_MIN_UNIQUE_CHARACTERS = 6


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
        hash_len=32,
        salt_len=16,
    )


def reset_hasher_cache() -> None:
    """Drop the cached hasher (settings changed, e.g. in tests)."""
    _hasher.cache_clear()


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time Argon2 verification that never raises on bad input."""
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher().check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def validate_password_strength(password: str) -> None:
    """Apply the platform password policy.

    Length is the dominant control (NIST SP 800-63B); the character checks only
    reject obviously degenerate inputs such as a repeated character.
    """
    if len(password) < settings.auth_min_password_length:
        raise ValidationError(
            f"Password must be at least {settings.auth_min_password_length} characters long.",
            code="weak_password",
            details={"field": "password", "min_length": settings.auth_min_password_length},
        )
    if password.lower() == password or password.upper() == password:
        raise ValidationError(
            "Password must mix upper and lower case characters.",
            code="weak_password",
            details={"field": "password"},
        )
    if len(set(password)) < _MIN_UNIQUE_CHARACTERS:
        raise ValidationError(
            "Password is too repetitive.",
            code="weak_password",
            details={"field": "password"},
        )
    if not re.search(r"[^A-Za-z]", password):
        raise ValidationError(
            "Password must contain at least one number or symbol.",
            code="weak_password",
            details={"field": "password"},
        )


def generate_token(nbytes: int) -> str:
    """Cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 digest of a bearer token (tokens are high-entropy, so no KDF)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, expected_hash: str) -> bool:
    """Constant-time comparison of a presented token against a stored hash."""
    if not token or not expected_hash:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)


def hash_client_ip(ip: str | None) -> str | None:
    """Pseudonymous client identifier for rate limiting and audit.

    The raw address is never stored; a truncated salted digest is enough to
    recognise abuse without retaining personal network data.
    """
    if not ip:
        return None
    salt = "loopmesh.ip.v1"
    return hashlib.sha256(f"{salt}:{ip}".encode("utf-8")).hexdigest()[:32]


def _trusted_proxy_networks(trusted_proxy_ips: list[str]):
    """Parse configured proxy IPs/CIDRs into networks; invalid entries are ignored."""
    import ipaddress

    networks = []
    for entry in trusted_proxy_ips:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return networks


def _ip_in_networks(ip: str | None, networks) -> bool:
    if not ip:
        return False
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return any(addr in network for network in networks)


def resolve_client_ip(
    request,
    *,
    trust_proxy_headers: bool | None = None,
    trusted_proxy_ips: list[str] | None = None,
) -> str | None:
    """Return the originating client IP, trusting forwarded headers only from proxies.

    When proxy-header trust is disabled (the default) or the direct peer is not
    an explicitly trusted proxy, the peer address is returned and any
    X-Forwarded-For header is ignored. When enabled, the chain is resolved
    right-to-left and the first non-trusted hop is returned, so a client cannot
    spoof its identity by prepending arbitrary values. If every hop in the chain
    is trusted, the leftmost value is returned as a last resort.
    """
    peer = request.client.host if getattr(request, "client", None) else None
    if trust_proxy_headers is None:
        trust_proxy_headers = settings.trust_proxy_headers
    if trusted_proxy_ips is None:
        trusted_proxy_ips = settings.trusted_proxy_ip_list

    networks = _trusted_proxy_networks(trusted_proxy_ips)
    if not trust_proxy_headers or not networks or not _ip_in_networks(peer, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return peer

    hops = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not hops:
        return peer

    for hop in reversed(hops):
        if not _ip_in_networks(hop, networks):
            return hop
    return hops[0]


def normalise_email(email: str) -> str:
    return email.strip().lower()
