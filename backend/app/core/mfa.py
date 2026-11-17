"""Platform operator MFA primitives: TOTP, secret encryption and recovery codes.

Secrets are encrypted with an authenticated, versioned Fernet envelope:
``v1.<key-id>.<ciphertext>``.  The key ID is a truncated SHA-256 fingerprint,
not key material; it lets an operator see which key sealed each row while a
primary key and an explicit previous-key list are configured during rotation.

Fail-closed rules:

* without a usable primary key every enrolment/verification path raises
  ``mfa_unavailable`` — there is no plaintext fallback and no bypass;
* a malformed or unknown key identifier is refused; unreadable ciphertext is
  never replaced with a fresh secret;
* legacy unversioned Fernet tokens remain readable during migration;
* a TOTP code is accepted once: the last accepted time-step is stored per user;
* recovery codes are stored only as SHA-256 hashes and consumed once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError

TOTP_STEP_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW_STEPS = 1
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ENVELOPE_PREFIX = "v1"
_KEY_ID_LENGTH = 16


class MfaUnavailableError(AppError):
    status_code = 503
    code = "mfa_unavailable"


class MfaKeyRotationError(AppError):
    status_code = 500
    code = "mfa_key_rotation_failed"


@dataclass(frozen=True, slots=True)
class _KeyMaterial:
    key_id: str
    fernet: Fernet


@dataclass(frozen=True, slots=True)
class _Keyring:
    primary: _KeyMaterial
    by_id: dict[str, _KeyMaterial]
    previous_ids: tuple[str, ...]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:_KEY_ID_LENGTH]


def _validated_key(raw: str, *, purpose: str) -> _KeyMaterial:
    key = (raw or "").strip()
    if not key:
        raise MfaUnavailableError(
            "Platform MFA is not configured on this deployment.",
            details={"reason": "mfa_key_missing"},
        )
    try:
        fernet = Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise MfaUnavailableError(
            "Platform MFA is misconfigured on this deployment.",
            details={"reason": f"mfa_{purpose}_invalid"},
        ) from exc
    return _KeyMaterial(key_id=_fingerprint(key), fernet=fernet)


@lru_cache(maxsize=1)
def _keyring() -> _Keyring:
    primary = _validated_key(settings.mfa_encryption_key or "", purpose="key")
    previous_raw = (settings.mfa_encryption_previous_keys or "").split(",")
    previous: list[_KeyMaterial] = []
    seen = {primary.key_id}
    for value in previous_raw:
        if not value.strip():
            continue
        material = _validated_key(value, purpose="previous_key")
        if material.key_id in seen:
            continue
        seen.add(material.key_id)
        previous.append(material)
    by_id = {primary.key_id: primary}
    by_id.update({item.key_id: item for item in previous})
    return _Keyring(
        primary=primary,
        by_id=by_id,
        previous_ids=tuple(item.key_id for item in previous),
    )


def reset_mfa_key_cache() -> None:
    """Drop the cached keyring (settings changed, e.g. in tests)."""
    _keyring.cache_clear()


def active_key_id() -> str:
    return _keyring().primary.key_id


def previous_key_ids() -> tuple[str, ...]:
    return _keyring().previous_ids


def generate_totp_secret() -> str:
    """A 160-bit Base32 secret, the conventional TOTP size."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str) -> str:
    keyring = _keyring()
    token = keyring.primary.fernet.encrypt(secret.encode("ascii")).decode("ascii")
    return f"{ENVELOPE_PREFIX}.{keyring.primary.key_id}.{token}"


def encryption_key_id(encrypted: str | None) -> str:
    """Return the envelope key ID, or ``legacy`` for an old Fernet token."""
    value = (encrypted or "").strip()
    if not value:
        return "missing"
    parts = value.split(".", 2)
    if len(parts) == 3 and parts[0] == ENVELOPE_PREFIX:
        return parts[1] or "unknown"
    return "legacy"


def decrypt_secret(encrypted: str) -> str:
    value = (encrypted or "").strip()
    if not value:
        raise MfaUnavailableError(
            "The stored MFA secret cannot be read with the configured key.",
            details={"reason": "mfa_secret_missing"},
        )

    keyring = _keyring()
    if value.startswith(f"{ENVELOPE_PREFIX}."):
        parts = value.split(".", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise MfaUnavailableError(
                "The stored MFA secret has an invalid encryption envelope.",
                details={"reason": "mfa_secret_envelope_invalid"},
            )
        material = keyring.by_id.get(parts[1])
        if material is None:
            raise MfaUnavailableError(
                "The stored MFA secret was encrypted with a key that is not configured.",
                details={"reason": "mfa_key_not_configured"},
            )
        try:
            return material.fernet.decrypt(parts[2].encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError, UnicodeDecodeError) as exc:
            raise MfaUnavailableError(
                "The stored MFA secret cannot be read with the configured key.",
                details={"reason": "mfa_secret_unreadable"},
            ) from exc

    # Batch 12 tokens had no version envelope. Try the primary and explicit
    # previous keys; never overwrite the value if none succeeds.
    for material in [keyring.primary, *keyring.by_id.values()]:
        try:
            return material.fernet.decrypt(value.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError, UnicodeDecodeError):
            continue
    raise MfaUnavailableError(
        "The stored MFA secret cannot be read with the configured key.",
        details={"reason": "mfa_secret_unreadable"},
    )


@dataclass(frozen=True, slots=True)
class RotationStatus:
    active_key_id: str
    previous_key_ids: tuple[str, ...]
    total_secrets: int
    active: int
    legacy: int
    previous: int
    unknown: int

    @property
    def complete(self) -> bool:
        return self.total_secrets == self.active

    @property
    def needs_rotation(self) -> int:
        return self.total_secrets - self.active


def rotation_status(db: Session) -> RotationStatus:
    """Count stored envelopes by key ID without ever decrypting or printing one."""
    keyring = _keyring()
    from app.db.models.identity import User

    counts = {"active": 0, "legacy": 0, "previous": 0, "unknown": 0}
    total = 0
    for (encrypted,) in db.execute(
        select(User.mfa_secret_encrypted).where(User.mfa_secret_encrypted.is_not(None))
    ):
        total += 1
        key_id = encryption_key_id(encrypted)
        if key_id == keyring.primary.key_id:
            counts["active"] += 1
        elif key_id == "legacy":
            counts["legacy"] += 1
        elif key_id in keyring.previous_ids:
            counts["previous"] += 1
        else:
            counts["unknown"] += 1
    return RotationStatus(
        active_key_id=keyring.primary.key_id,
        previous_key_ids=keyring.previous_ids,
        total_secrets=total,
        active=counts["active"],
        legacy=counts["legacy"],
        previous=counts["previous"],
        unknown=counts["unknown"],
    )


@dataclass(frozen=True, slots=True)
class RotationResult:
    total: int
    rotated: int
    already_active: int
    batches: int


def rotate_mfa_secrets(
    db: Session,
    *,
    batch_size: int = 100,
    commit: bool = True,
) -> RotationResult:
    """Re-encrypt every stored secret under the active primary key.

    Rows are processed in stable UUID order and committed one batch at a time.
    An invalid/missing key or corrupted ciphertext aborts the current batch and
    is never replaced by a new secret.  Earlier committed batches stay rotated,
    so the command is safe to resume.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    from app.db.models.identity import User

    active_id = active_key_id()
    total = rotated = already = batches = 0
    last_id = None
    while True:
        statement = select(User).where(User.mfa_secret_encrypted.is_not(None))
        if last_id is not None:
            statement = statement.where(User.id > last_id)
        statement = statement.order_by(User.id.asc()).limit(batch_size)
        rows = list(db.scalars(statement).all())
        if not rows:
            break
        try:
            for user in rows:
                total += 1
                if encryption_key_id(user.mfa_secret_encrypted) == active_id:
                    already += 1
                    continue
                secret = decrypt_secret(user.mfa_secret_encrypted or "")
                user.mfa_secret_encrypted = encrypt_secret(secret)
                rotated += 1
            if commit:
                db.commit()
            else:
                db.flush()
            batches += 1
        except MfaUnavailableError:
            db.rollback()
            raise
        except Exception as exc:
            db.rollback()
            raise MfaKeyRotationError(
                "MFA key rotation stopped; the current batch was rolled back.",
                details={"reason": "mfa_rotation_interrupted"},
            ) from exc
        last_id = rows[-1].id
    return RotationResult(
        total=total,
        rotated=rotated,
        already_active=already,
        batches=batches,
    )


def _decode_secret(secret: str) -> bytes:
    padded = secret.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded)


def hotp(secret: str, counter: int, *, digits: int = TOTP_DIGITS) -> str:
    digest = hmac.new(
        _decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**digits)).zfill(digits)


def counter_for(moment: datetime | None = None) -> int:
    stamp = moment or utcnow()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return int(stamp.timestamp()) // TOTP_STEP_SECONDS


def totp_at(secret: str, moment: datetime | None = None) -> str:
    return hotp(secret, counter_for(moment))


def verify_totp(
    secret: str,
    code: str,
    *,
    moment: datetime | None = None,
    last_counter: int | None = None,
) -> int | None:
    """Return the accepted time-step, or ``None``.

    A code from the previous or next step is accepted to tolerate clock skew,
    but only if it is strictly newer than the last accepted step. That single
    rule prevents replaying a code within the skew window.
    """
    submitted = (code or "").strip().replace(" ", "")
    if not submitted.isdigit() or len(submitted) != TOTP_DIGITS:
        return None
    current = counter_for(moment)
    for offset in range(-TOTP_WINDOW_STEPS, TOTP_WINDOW_STEPS + 1):
        candidate = current + offset
        if last_counter is not None and candidate <= last_counter:
            continue
        if hmac.compare_digest(hotp(secret, candidate), submitted):
            return candidate
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str = "LOOPMESH") -> str:
    from urllib.parse import quote, urlencode

    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_STEP_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"


def normalise_recovery_code(code: str) -> str:
    return "".join(character for character in (code or "").upper() if character.isalnum())


def hash_recovery_code(code: str) -> str:
    normalised = normalise_recovery_code(code)
    return hashlib.sha256(f"loopmesh.recovery.v1:{normalised}".encode("utf-8")).hexdigest()


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-transcribable single-use codes (no ambiguous characters)."""
    codes: list[str] = []
    while len(codes) < count:
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        code = f"LM-{raw[:4]}-{raw[4:]}"
        if code not in codes:
            codes.append(code)
    return codes


def generate_fernet_key() -> str:
    """Key-generation helper for operators and deployment tooling."""
    return Fernet.generate_key().decode("ascii")
