"""Application configuration.

All runtime configuration is read from environment variables (optionally via a
``backend/.env`` file). Secrets are never hardcoded and never shipped to the
frontend.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ — used to resolve the local SQLite fallback and the .env file.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- application -------------------------------------------------------
    app_name: str = "LOOPMESH API"
    app_description: str = (
        "REST API for LOOPMESH — an intelligent industrial resource recovery "
        "platform. Phase 1 exposes material intelligence, deterministic "
        "compatibility screening, requirement-based discovery, a recovery "
        "ledger and agent/optimization readiness endpoints."
    )
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"

    # --- database ----------------------------------------------------------
    # PostgreSQL is the target. When DATABASE_URL is unset we fall back to a
    # local SQLite file so the demo can be started without a database server.
    database_url: str = Field(
        default=f"sqlite:///{(BACKEND_DIR / 'loopmesh_dev.db').as_posix()}"
    )
    database_echo: bool = False
    database_pool_size: int = 5
    database_pool_max_overflow: int = 10

    # --- HTTP --------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Comma-separated Host header allow-list. Defaults cover local development
    # and FastAPI's TestClient ("testserver"); production must set an explicit
    # non-empty list of real hostnames.
    allowed_hosts: str = "localhost,127.0.0.1,testserver"
    request_id_header: str = "X-Request-ID"

    # --- proxy trust -------------------------------------------------------
    # Forwarded headers (e.g. X-Forwarded-For) are only honoured when the
    # direct peer is an explicitly trusted proxy. Disabled by default so a
    # client can never spoof its address by sending arbitrary headers.
    trust_proxy_headers: bool = False
    # Comma-separated trusted proxy IPs and/or CIDR ranges (e.g.
    # "127.0.0.1,10.0.0.0/8"). Ignored unless trust_proxy_headers is true.
    # Wildcards ("*", "0.0.0.0/0" used as a trust-everything shortcut) are
    # never allowed; list only the actual proxy hops you operate.
    trusted_proxy_ips: str = ""

    # --- logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # --- discovery / compatibility ----------------------------------------
    discovery_min_score: int = Field(default=55, ge=0, le=100)
    discovery_max_pairs: int = Field(default=2000, ge=1, le=100_000)

    # --- authentication ----------------------------------------------------
    # Opaque server-side sessions: a short-lived access token plus a rotating
    # refresh token. Only hashes are stored in the database.
    auth_access_ttl_minutes: int = Field(default=15, ge=1, le=120)
    auth_refresh_ttl_days: int = Field(default=30, ge=1, le=365)
    auth_invitation_ttl_days: int = Field(default=7, ge=1, le=30)
    auth_reset_ttl_minutes: int = Field(default=30, ge=5, le=240)
    auth_max_failed_logins: int = Field(default=5, ge=3, le=20)
    auth_lockout_minutes: int = Field(default=15, ge=1, le=240)
    auth_min_password_length: int = Field(default=12, ge=8, le=128)

    # Cookie transport. `Secure` is forced on in production by validation below.
    auth_cookie_secure: bool = False
    auth_cookie_domain: str | None = None
    auth_session_cookie: str = "lm_session"
    auth_refresh_cookie: str = "lm_refresh"
    auth_csrf_cookie: str = "lm_csrf"
    auth_csrf_header: str = "X-CSRF-Token"

    # Shared, database-backed fixed-window limiter. The database row is the
    # authority across workers; see app/core/security_limiter.py. It fails
    # closed if unavailable. The local limiter remains a development fallback
    # primitive but is not used for authentication decisions.
    auth_login_attempts_per_hour: int = Field(default=20, ge=1, le=1000)
    auth_reset_attempts_per_hour: int = Field(default=5, ge=1, le=100)
    security_limiter_retention_hours: int = Field(default=24, ge=1, le=720)

    # --- platform MFA and governance --------------------------------------
    # Fernet key (url-safe base64, 32 bytes) used to encrypt TOTP secrets at
    # rest. There is deliberately no default: when it is absent, MFA enrolment
    # and verification fail closed rather than silently disabling the gate.
    # During rotation, the new key is primary and old keys are listed in
    # MFA_ENCRYPTION_PREVIOUS_KEYS (comma separated) until rotation completes.
    mfa_encryption_key: str | None = None
    mfa_encryption_previous_keys: str = ""
    mfa_rotation_batch_size: int = Field(default=100, ge=1, le=1000)
    mfa_max_failed_attempts: int = Field(default=5, ge=3, le=20)
    mfa_lockout_minutes: int = Field(default=15, ge=1, le=240)
    mfa_attempts_per_5_minutes: int = Field(default=10, ge=3, le=100)

    # Two-person approval for protected platform operations.
    platform_approval_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    platform_session_idle_minutes: int = Field(default=30, ge=5, le=120)
    platform_session_absolute_hours: int = Field(default=8, ge=1, le=24)

    # Bounded audit export/archive and chain verification.
    platform_audit_export_max_rows: int = Field(default=5000, ge=100, le=20_000)
    platform_audit_export_max_range_days: int = Field(default=90, ge=1, le=365)
    audit_verify_batch_size: int = Field(default=500, ge=50, le=5000)
    audit_archive_batch_size: int = Field(default=500, ge=50, le=5000)

    # Argon2id parameters. Reduced in tests via environment overrides.
    argon2_time_cost: int = Field(default=3, ge=1, le=10)
    argon2_memory_cost: int = Field(default=65536, ge=8192, le=262144)
    argon2_parallelism: int = Field(default=2, ge=1, le=8)

    # --- AI (server-side only, unused in Phase 1) --------------------------
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("database_url")
    @classmethod
    def _select_postgres_driver(cls, value: str) -> str:
        """Select the installed psycopg 3 driver for provider-issued URLs.

        Managed platforms hand out ``postgresql://`` (some legacy tooling still
        emits ``postgres://``). SQLAlchemy maps both schemes to psycopg2, which
        this project does not install. Rewriting the scheme to
        ``postgresql+psycopg://`` selects the pinned psycopg 3 driver, so a
        connection string copied from a hosting dashboard works unedited.
        """
        url = value.strip()
        for prefix in ("postgres://", "postgresql://"):
            if url.lower().startswith(prefix):
                url = f"postgresql+psycopg://{url[len(prefix):]}"
                break
        allowed = ("postgresql+psycopg://", "sqlite:")
        if not url.lower().startswith(allowed):
            raise ValueError(
                "DATABASE_URL must be a PostgreSQL URL (postgresql:// or "
                "postgresql+psycopg://) or sqlite://"
            )
        return url

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
        return level

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        """Allowed Host header values as a clean list."""
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def trusted_proxy_ip_list(self) -> list[str]:
        """Trusted proxy IPs/CIDRs as a clean list."""
        return [value.strip() for value in self.trusted_proxy_ips.split(",") if value.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite:")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        """Secure cookies are mandatory in production, optional over plain HTTP locally."""
        return True if self.is_production else self.auth_cookie_secure

    @property
    def same_site(self) -> str:
        return "lax"

    @property
    def ai_enabled(self) -> bool:
        """Gemini integration is intentionally not wired in Phase 1."""
        return bool(self.gemini_api_key)

    def validate_runtime_security(self) -> None:
        """Raise if essential production security settings are unsafe."""
        if not self.is_production:
            return
        problems: list[str] = []
        if self.is_sqlite:
            problems.append("DATABASE_URL must point to PostgreSQL in production.")
        origins = self.cors_origin_list
        if not origins or any(o == "*" for o in origins):
            problems.append("CORS_ORIGINS must be an explicit allow-list in production.")
        if any(o.startswith("http://") for o in origins):
            problems.append("CORS_ORIGINS must use https:// in production.")
        if self.debug:
            problems.append("DEBUG must be disabled in production.")
        if self.mfa_encryption_key is not None and len(self.mfa_encryption_key) < 32:
            problems.append("MFA_ENCRYPTION_KEY is set but too short to be a Fernet key.")
        hosts = self.allowed_host_list
        if not hosts or any(host == "*" for host in hosts):
            problems.append(
                "ALLOWED_HOSTS must be an explicit non-empty allow-list in production."
            )
        if any(any(ch.isspace() for ch in host) for host in hosts):
            problems.append("ALLOWED_HOSTS entries must not contain whitespace.")
        trusted_proxies = self.trusted_proxy_ip_list
        if any(entry in {"*", "0.0.0.0/0", "::/0"} for entry in trusted_proxies):
            problems.append(
                "TRUSTED_PROXY_IPS must list explicit proxy IPs/CIDRs; wildcards are not allowed."
            )
        if self.trust_proxy_headers and not trusted_proxies:
            problems.append(
                "TRUSTED_PROXY_IPS must be configured when TRUST_PROXY_HEADERS is enabled."
            )
        if self.trust_proxy_headers and trusted_proxies:
            import ipaddress

            for entry in trusted_proxies:
                try:
                    ipaddress.ip_network(entry, strict=False)
                except ValueError:
                    problems.append(
                        f"TRUSTED_PROXY_IPS contains an invalid IP/CIDR entry: {entry!r}."
                    )
        if problems:
            raise RuntimeError("Unsafe production configuration: " + " ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (safe to use as a FastAPI dependency)."""
    return Settings()


settings = get_settings()
