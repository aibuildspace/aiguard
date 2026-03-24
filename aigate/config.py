from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="GUARD_",
        env_file_encoding="utf-8",
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 8080
    workers: int = 1
    log_level: str = "info"
    debug: bool = False

    # Runtime mode: "dev" (full access) or "prod" (locked-down)
    # Override with GUARD_MODE=prod or --mode flag on CLI
    mode: Literal["dev", "prod"] = "dev"

    # Database — SQLite by default, zero config
    # Override: GUARD_DATABASE_URL=postgresql+asyncpg://user:pass@host/db
    database_url: str = "sqlite+aiosqlite:///./aigate.db"

    # Encryption key for upstream API keys at rest (Fernet/AES-128-CBC)
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str = ""

    # Shield directories (colon-separated, like PATH)
    shields_dirs: str = "./shields:./user_shields"

    # Upstream API base URLs
    anthropic_base_url: str = "https://api.anthropic.com"
    openai_base_url: str = "https://api.openai.com"

    # Passthrough mode: client's real API key is forwarded as-is.
    # When False (key-vault mode), aigate resolves the upstream key from DB.
    passthrough_mode: bool = True

    # Admin management API
    admin_api_enabled: bool = True
    admin_api_key: str = ""

    # Allowed CORS origins in prod mode (comma-separated)
    # Dev mode always uses "*"
    cors_origins: str = ""

    # Audit settings
    audit_store_request_body: bool = False
    audit_store_response_body: bool = False
    audit_retention_days: int = 90

    # HTTP client timeouts (seconds)
    upstream_connect_timeout: float = 10.0
    upstream_read_timeout: float = 120.0

    @property
    def shields_dir_list(self) -> list[str]:
        return [d.strip() for d in self.shields_dirs.split(":") if d.strip()]


settings = Settings()
