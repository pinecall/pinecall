"""Settings: every variable the gateway, the worker and the runner read, loaded once."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pinecall_runtime.enums import Env
from pinecall_runtime.exceptions import ConfigurationError

type Role = Literal["all", "gateway", "worker"]

# Slug-shaped, never empty: an empty agent_name makes LiveKit dispatch to every room.
A_FLEET_NAME = r"^[a-z0-9][a-z0-9-]{0,62}$"

# Spoken by the overflow agent when every worker is full, before hanging up.
OVERFLOW_SAYS = (
    "En este momento todas nuestras líneas están ocupadas. Hemos tomado nota de su número "
    "y le devolveremos la llamada en cuanto se libere una. Gracias por su paciencia."
)


class Settings(BaseSettings):
    """The process's configuration, from systemd credentials, a .env and the environment."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore", populate_by_name=True, env_file_encoding="utf-8")

    # ── LiveKit, the media plane ──
    livekit_url: str = Field("ws://127.0.0.1:7880", alias="LIVEKIT_URL")
    livekit_sandbox_url: str | None = Field(None, alias="LIVEKIT_SANDBOX_URL")
    livekit_api_key: str | None = Field(None, alias="LIVEKIT_API_KEY")
    livekit_api_secret: SecretStr | None = Field(None, alias="LIVEKIT_API_SECRET")
    livekit_public_url: str | None = Field(None, alias="LIVEKIT_PUBLIC_URL")
    domain: str | None = Field(None, alias="PINECALL_DOMAIN")
    sip_domain: str | None = Field(None, alias="PINECALL_SIP_DOMAIN")
    sandbox_sip_domain: str | None = Field(None, alias="PINECALL_SANDBOX_SIP_DOMAIN")

    # ── Postgres ──
    database_url: SecretStr = Field(
        SecretStr("postgresql://pinecall:pinecall@127.0.0.1:5432/pinecall"), alias="DATABASE_URL"
    )
    db_app_role: str | None = Field(None, alias="PINECALL_DB_APP_ROLE")
    db_pool: int = Field(10, alias="PINECALL_DB_POOL", ge=3)

    # ── Redis, the signal between gateways ──
    redis_url: SecretStr | None = Field(None, alias="PINECALL_REDIS_URL")

    # ── recordings and the object store ──
    recordings_root: str = Field("recordings", alias="PINECALL_RECORDINGS")
    recordings_bucket: str | None = Field(None, alias="PINECALL_RECORDINGS_BUCKET")
    wal_spool: str | None = Field("/var/lib/pinecall/wal", alias="PINECALL_WAL_SPOOL")
    s3_endpoint: str | None = Field(None, alias="PINECALL_S3_ENDPOINT")
    s3_region: str | None = Field(None, alias="PINECALL_S3_REGION")
    s3_access_key_id: str | None = Field(None, alias="PINECALL_S3_ACCESS_KEY_ID")
    s3_secret_access_key: SecretStr | None = Field(None, alias="PINECALL_S3_SECRET_ACCESS_KEY")

    # ── the gateway ──
    gateway_url: str = Field("http://127.0.0.1:8080", alias="PINECALL_GATEWAY_URL")
    gateway_listen: str | None = Field(None, alias="PINECALL_GATEWAY_LISTEN")
    trusted_proxies: str = Field("127.0.0.1", alias="PINECALL_TRUSTED_PROXIES")
    metrics_from: str = Field("127.0.0.1,::1", alias="PINECALL_METRICS_FROM")
    app_origins: str = Field("", alias="PINECALL_APP_ORIGINS")
    ops_key: SecretStr | None = Field(None, alias="PINECALL_OPS_KEY")
    token_key: SecretStr | None = Field(None, alias="PINECALL_TOKEN_KEY")
    vault_key: SecretStr | None = Field(None, alias="PINECALL_VAULT_KEY")
    signup: bool = Field(False, alias="PINECALL_SIGNUP")
    # Cloudflare Turnstile on the doors a stranger knocks at (a password, a sign-up, a reset):
    # the site key the page draws the widget with, the secret the gateway verifies its token with.
    turnstile_site_key: str | None = Field(None, alias="PINECALL_TURNSTILE_SITE_KEY")
    turnstile_secret: SecretStr | None = Field(None, alias="PINECALL_TURNSTILE_SECRET")
    approve_hooked: bool = Field(False, alias="PINECALL_APPROVE_HOOKED")
    cloud: bool = Field(False, alias="PINECALL_CLOUD")
    billing_url: str | None = Field(None, alias="PINECALL_BILLING_URL")
    min_password: int = Field(8, alias="PINECALL_MIN_PASSWORD", ge=0)
    smtp_url: SecretStr | None = Field(None, alias="PINECALL_SMTP_URL")
    mail_from: str | None = Field(None, alias="PINECALL_MAIL_FROM")

    # ── the worker ──
    worker_key: SecretStr | None = Field(None, alias="PINECALL_WORKER_KEY")
    fleet: str = Field("pinecall", alias="PINECALL_FLEET", pattern=A_FLEET_NAME)
    agent: str | None = Field(None, alias="PINECALL_AGENT")
    app: str | None = Field(None, alias="PINECALL_APP")
    max_jobs: int | None = Field(None, alias="PINECALL_MAX_JOBS")
    idle_processes: int | None = Field(None, alias="PINECALL_IDLE_PROCESSES")
    worker_http_host: str = Field("127.0.0.1", alias="PINECALL_WORKER_HTTP_HOST")
    worker_http_port: int = Field(8082, alias="PINECALL_WORKER_HTTP_PORT")
    worker_name: str | None = Field(None, alias="PINECALL_WORKER_NAME")
    notify_socket: str | None = Field(None, alias="NOTIFY_SOCKET")
    overflow_says: str = Field(OVERFLOW_SAYS, alias="PINECALL_OVERFLOW_SAYS")

    # ── the runner of hosted apps ──
    runner_key: SecretStr | None = Field(None, alias="PINECALL_RUNNER_KEY")
    runner_image: str = Field("docker.io/library/node:24-slim", alias="PINECALL_RUNNER_IMAGE")
    runner_runtime_class: str = Field("gvisor", alias="PINECALL_RUNNER_RUNTIME_CLASS")
    runner_namespace: str = Field("pinecall-apps", alias="PINECALL_RUNNER_NAMESPACE")
    runner_sources_url: str = Field("http://127.0.0.1:8080", alias="PINECALL_RUNNER_SOURCES_URL")
    runner_listen: str = Field("127.0.0.1", alias="PINECALL_RUNNER_LISTEN")
    runner_port: int = Field(8080, alias="PINECALL_RUNNER_PORT")
    # Where the runner runs each host: a gVisor pod on the hosting cluster, or a process of this
    # machine, unfenced, for a runtime whose apps are its owner's own (`local up`).
    runner_engine: Literal["cluster", "processes"] = Field("cluster", alias="PINECALL_RUNNER_ENGINE")
    runner_home: Path = Field(Path.home() / ".pinecall-runtime" / "apps", alias="PINECALL_RUNNER_HOME")

    # ── observability ──
    role: Role = Field("all", alias="PINECALL_ROLE")
    log_level: str = Field("INFO", alias="PINECALL_LOG_LEVEL")
    log_format: Literal["text", "json"] = Field("text", alias="PINECALL_LOG_FORMAT")
    otlp_endpoint: str | None = Field(None, alias="PINECALL_OTLP_ENDPOINT")
    otlp_headers: SecretStr | None = Field(None, alias="PINECALL_OTLP_HEADERS")
    otlp_pii: bool = Field(False, alias="PINECALL_OTLP_PII")
    timezone: str = Field("UTC", alias="PINECALL_TIMEZONE")

    # ── retrieval budgets; None is the session's default ──
    voice_lookup_budget_ms: int | None = Field(None, alias="PINECALL_VOICE_LOOKUP_BUDGET_MS")
    text_lookup_budget_ms: int | None = Field(None, alias="PINECALL_TEXT_LOOKUP_BUDGET_MS")
    remember_budget_s: float | None = Field(None, alias="PINECALL_REMEMBER_BUDGET_S")

    # Vendor keys keep the vendor's own variable name (ANTHROPIC_API_KEY); the providers catalog
    # asks for them by name, so every variable read is kept.
    variables: dict[str, str] = Field(default_factory=dict, repr=False)

    @field_validator("timezone")
    @classmethod
    def _an_iana_zone(cls, zone: str) -> str:
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"{zone!r} is not an IANA time zone (Europe/Madrid, UTC)") from None
        return zone

    @model_validator(mode="after")
    def _a_bucket_names_its_store(self) -> "Settings":
        named = {
            "PINECALL_S3_ENDPOINT": self.s3_endpoint,
            "PINECALL_S3_REGION": self.s3_region,
            "PINECALL_S3_ACCESS_KEY_ID": self.s3_access_key_id,
            "PINECALL_S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
        }
        missing = [name for name, value in named.items() if value is None]
        if self.recordings_bucket is not None and missing:
            raise ValueError(f"PINECALL_RECORDINGS_BUCKET needs {', '.join(missing)}")
        return self

    # A secret without a site key would refuse every password while the page shows no widget;
    # a site key without a secret would draw a widget nothing verifies.
    @model_validator(mode="after")
    def _turnstile_is_both_keys_or_neither(self) -> "Settings":
        if (self.turnstile_site_key is None) != (self.turnstile_secret is None):
            raise ValueError("PINECALL_TURNSTILE_SITE_KEY and PINECALL_TURNSTILE_SECRET are set together, or neither")
        return self

    @property
    def address(self) -> str | None:
        """The https address of the box's name, or None where it has none."""
        return None if self.domain is None else f"https://{self.domain}"

    def livekit_url_of(self, env: Env) -> str:
        """The LiveKit that env's rooms live on, as this process reaches it."""
        if env is Env.sandbox and self.livekit_sandbox_url:
            return self.livekit_sandbox_url
        return self.livekit_url

    def browser_livekit_url(self, env: Env) -> str:
        """The LiveKit URL a browser joins for a call of the env: a LiveKit of the operator's own wins over the name."""
        own = self.livekit_sandbox_url if env is Env.sandbox else None
        if own:
            return f"wss://{self.domain}/sandbox" if self.domain else own
        if self.livekit_public_url:
            return self.livekit_public_url
        return f"wss://{self.domain}" if self.domain else self.livekit_url

    def sip_domain_of(self, env: Env) -> str | None:
        """The name a carrier sends that env's calls to: its SIP name, else the box's name."""
        named = self.sandbox_sip_domain if env is Env.sandbox else self.sip_domain
        return named or self.sip_domain or self.domain

    def database_dsn(self, driver: str = "asyncpg") -> str:
        """The DSN for SQLAlchemy, on the given driver."""
        url = self.database_url.get_secret_value()
        return url.replace("postgresql://", f"postgresql+{driver}://", 1)


def load_settings() -> Settings:
    """Build Settings from the systemd credentials, the .env files found and the environment."""
    read: dict[str, str] = {}
    credentials = os.environ.get("CREDENTIALS_DIRECTORY")
    if credentials:
        read.update(_credentials_in(Path(credentials)))
    for file in _env_files():
        read.update(_env_file(file))
    read.update(os.environ)
    # A bare `NAME=` means unset, so a copied example never hands a vendor an empty value.
    variables = {name: value for name, value in read.items() if value != ""}
    try:
        return Settings.model_validate({**variables, "variables": variables})
    except ValueError as refused:
        raise ConfigurationError(str(refused)) from refused


@lru_cache(maxsize=1)
def settings() -> Settings:
    """The process's settings, loaded once."""
    return load_settings()


# `.env` in the first directory up to the repository root that has one; `runtime/.env` too, for a
# process started from the checkout root. Bounded at `.git`: a stray .env above would load wrong keys.
def _env_files() -> list[Path]:
    folder = Path.cwd().resolve()
    for candidate in (folder, *folder.parents):
        found = [candidate / name for name in (".env", "runtime/.env") if (candidate / name).is_file()]
        if found:
            return found
        if (candidate / ".git").exists():
            return []
    return []


def _credentials_in(directory: Path) -> dict[str, str]:
    return {
        file.name: file.read_text(encoding="utf-8").strip() for file in sorted(directory.iterdir()) if file.is_file()
    }


def _env_file(path: Path) -> dict[str, str]:
    from dotenv import dotenv_values

    try:
        values = dotenv_values(path, encoding="utf-8")
    except OSError as failed:
        raise ConfigurationError(f"cannot read {path}: {failed}") from failed
    return {name: value for name, value in values.items() if value is not None}
