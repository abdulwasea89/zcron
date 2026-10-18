"""Application configuration.

Settings are loaded from environment variables (and an optional .env file) via
pydantic-settings. Every external integration degrades to a deterministic local
"stub" mode when its credentials are absent, so the backend runs end-to-end with
zero external accounts. Provide real keys to activate real calls.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

import os

from dotenv import load_dotenv

load_dotenv()

# asyncpg does not understand libpq query params like ``sslmode`` /
# ``channel_binding`` (those belong to psycopg). Neon/Supabase copy-paste URLs
# ship them, so we strip them here and enable TLS via connect_args instead.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "options", "gssencmode"}


def _normalize_pg_url(url: str) -> str:
    """Coerce a pasted Postgres URL into an asyncpg-compatible SQLAlchemy URL.

    - ``postgres://`` / ``postgresql://`` -> ``postgresql+asyncpg://``
    - drops libpq-only query params (``sslmode``, ``channel_binding``, ...)
    """

    parts = urlsplit(url)
    scheme = parts.scheme
    if scheme in ("postgres", "postgresql"):
        scheme = "postgresql+asyncpg"

    kept = [
        pair
        for pair in parts.query.split("&")
        if pair and pair.split("=", 1)[0].lower() not in _LIBPQ_ONLY_PARAMS
    ]
    query = "&".join(kept)

    return urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    app_env: str = "development"
    app_name: str = "Gym Operations Platform"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    # --------------------------------------------------------------- security
    secret_key: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    remember_device_days: int = 30
    email_code_expire_minutes: int = 10
    magic_link_expire_minutes: int = 15
    password_reset_expire_minutes: int = 60

    max_login_attempts: int = 10
    login_lockout_minutes: int = 30
    failed_login_window_minutes: int = 15

    # --------------------------------------------------------------- database
    # Toggle: USE_CLOUD_DB=yes -> use CLOUD_DATABASE_URL (Neon/Supabase Postgres).
    #         USE_CLOUD_DB=no  -> use the local SQLite file (default, no services).
    use_cloud_db: bool = os.getenv("USE_CLOUD_DB", "no").strip().lower() in (
        "1",
        "yes",
        "true",
        "on",
    )
    # Paste your Neon connection string here (or in .env as CLOUD_DATABASE_URL).
    cloud_database_url: str = os.getenv("CLOUD_DATABASE_URL", "")
    # Local fallback file used when USE_CLOUD_DB is off.
    local_database_url: str = os.getenv(
        "LOCAL_DATABASE_URL", "sqlite+aiosqlite:///./gym_platform.db"
    )
    db_echo: bool = False

    @property
    def database_url(self) -> str:
        """Active database URL, chosen by the ``USE_CLOUD_DB`` toggle."""
        if self.use_cloud_db:
            if not self.cloud_database_url:
                raise RuntimeError(
                    "USE_CLOUD_DB is enabled but CLOUD_DATABASE_URL is empty. "
                    "Paste your Neon connection string into .env."
                )
            return _normalize_pg_url(self.cloud_database_url)
        return self.local_database_url

    # ------------------------------------------------------------------ redis
    redis_url: str = "redis://localhost:6379/0"

    # ----------------------------------------------------------------- stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_connect_webhook_secret: str = ""
    stripe_connect_client_id: str = ""

    # ------------------------------------------------------------- web front
    # Public base URL of the Next.js portal. Used to build links that land in
    # invite emails, so the recipient can complete the flow in a browser.
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # ------------------------------------------------------ email / push / ai
    email_from: str = "no-reply@example.com"
    smtp_url: str = ""
    # SMTP (e.g. Gmail): sends real mail to any recipient without a verified
    # sending domain. Set these to enable; takes precedence over Resend.
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "1") != "0"
    resend_api_key: str | None = os.getenv("RESEND_API_KEY")
    # Inbox provider credentials are Fernet-encrypted per workspace; keep this
    # key stable and use the base URL when providers need inbound webhooks.
    inbox_public_webhook_base_url: str = os.getenv("INBOX_PUBLIC_WEBHOOK_BASE_URL", "")
    inbox_encryption_key: str = os.getenv("INBOX_ENCRYPTION_KEY", "")
    inbox_meta_graph_version: str = os.getenv("INBOX_META_GRAPH_VERSION", "v25.0")
    expo_push_url: str = "https://exp.host/--/api/v2/push/send"
    ocr_provider_api_key: str = ""
    openai_api_key: str = ""

    # ------------------------------------------------------------- assistant
    # The model and provider live behind app/agent/model.py; these are the
    # tuning knobs. Absent key => deterministic stub (same degrade-gracefully
    # convention as ocr.py / email.py). See ADR 018.
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    assistant_model: str = "openai/gpt-oss-120b"
    assistant_temperature: float = 1.0
    assistant_max_completion_tokens: int = 2048
    # How many prior turns to replay as conversation history.
    assistant_history_limit: int = 20
    # Ceiling on model/tool super-steps per turn; bounds a runaway loop.
    assistant_recursion_limit: int = 25
    # Whether a turn may fan out to the specialist swarm (ADR 019).
    #   "auto"   — the planner decides per question (the default)
    #   "always" — dispatch all 40 specialists on every turn (demos)
    #   "off"    — never plan; every turn takes the direct ReAct path
    assistant_swarm_mode: str = "auto"

    # ------------------------------------------------------------------- hibp
    hibp_api_url: str = "https://api.pwnedpasswords.com"
    hibp_enabled: bool = True

    # -------------------------------------------------------- business limits
    signup_max_per_ip_per_hour: int = 3
    signup_max_per_email_per_day: int = 2
    signup_max_per_org_code_per_day: int = 50
    email_resend_max_per_hour: int = 3

    idempotency_stuck_seconds: int = 30

    tier_starter_cap: int = 25
    tier_pro_cap: int = 100

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def stripe_live(self) -> bool:
        """True when a real Stripe key is configured (else stub mode)."""
        return bool(self.stripe_secret_key) and self.stripe_secret_key != "sk_test_xxx"

    @property
    def assistant_live(self) -> bool:
        """True when a real Groq key is configured (else deterministic stub)."""
        return bool(self.groq_api_key)

    @property
    def smtp_active(self) -> bool:
        """True when SMTP creds are configured (real delivery to any recipient)."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def smtp_sender(self) -> str:
        """From address for SMTP: explicit smtp_from, else the SMTP username."""
        return self.smtp_from or self.smtp_user

    @property
    def email_active(self) -> bool:
        """True when any real email provider (SMTP or Resend) is configured."""
        return self.smtp_active or bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
