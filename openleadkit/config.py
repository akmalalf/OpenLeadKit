"""Strongly typed application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, HttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from openleadkit.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Environment-backed settings with safe defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "OpenLeadKit"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    app_timezone: str = "UTC"
    app_project_url: HttpUrl = HttpUrl("https://github.com/akmalalf/OpenLeadKit")

    database_url: str
    test_database_url: str | None = None

    overpass_api_url: HttpUrl = HttpUrl("https://overpass-api.de/api/interpreter")
    nominatim_api_url: HttpUrl = HttpUrl("https://nominatim.openstreetmap.org")
    http_user_agent: str = "OpenLeadKit/0.1.0"
    http_connect_timeout_seconds: float = Field(10, ge=1, le=60)
    http_read_timeout_seconds: float = Field(30, ge=1, le=180)
    http_max_response_bytes: int = Field(5_000_000, ge=10_000, le=25_000_000)
    http_per_domain_delay_seconds: float = Field(2, ge=0, le=60)

    default_result_limit: int = Field(100, ge=1, le=500)
    max_result_limit: int = Field(500, ge=1, le=5_000)
    duplicate_name_threshold: float = Field(0.72, ge=0.1, le=1)

    excel_input_path: Path = Path("input/Website_Lead_Funnel_CRM.xlsx")
    excel_output_dir: Path = Path("exports")

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if not value.startswith(("postgresql+psycopg://", "postgresql://")):
            raise ValueError("DATABASE_URL must use PostgreSQL and Psycopg 3")
        return value

    @model_validator(mode="after")
    def validate_limits(self) -> Settings:
        if self.default_result_limit > self.max_result_limit:
            raise ValueError("DEFAULT_RESULT_LIMIT cannot exceed MAX_RESULT_LIMIT")
        return self

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def safe_path(self, configured: Path, *, directory: bool = False) -> Path:
        root = self.project_root.resolve()
        candidate = configured if configured.is_absolute() else root / configured
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            raise ConfigurationError("The path must remain inside the project directory")
        if directory:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    @property
    def excel_input(self) -> Path:
        return self.safe_path(self.excel_input_path)

    @property
    def excel_output(self) -> Path:
        return self.safe_path(self.excel_output_dir, directory=True)

    @property
    def masked_database_url(self) -> str:
        parts = urlsplit(self.database_url)
        hostname = parts.hostname or "unknown"
        port = f":{parts.port}" if parts.port else ""
        username = parts.username or "unknown"
        return urlunsplit((parts.scheme, f"{username}:***@{hostname}{port}", parts.path, "", ""))


@lru_cache
def get_settings() -> Settings:
    """Load settings once per process."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache for tests and Streamlit settings refresh."""
    get_settings.cache_clear()
