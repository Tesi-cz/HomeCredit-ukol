"""Konfigurace aplikace.

Veškeré nastavení pochází z proměnných prostředí (R1.6, R12.4). Chybějící
povinná hodnota shodí start aplikace s jasnou zprávou, místo aby se projevila
až za běhu — viz `load_settings`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typované nastavení čtené z prostředí a z `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Identita aplikace ---
    app_name: str = "REGINA"
    app_subtitle: str = "REGistr INterních Aplikací"
    base_url: str = "http://localhost:8000"

    # --- Databáze ---
    database_url: str
    database_connect_timeout_seconds: int = 5

    # --- Session ---
    # Podepsaná cookie, žádná tabulka sessions (database.md sekce 8).
    session_secret: str = Field(min_length=32)
    session_cookie_name: str = "regina_session"
    session_cookie_secure: bool = True
    session_max_age_seconds: int = 8 * 60 * 60

    # --- Poskytovatel identity (OIDC) ---
    # Endpointy se nikam nezapisují, čtou se z discovery dokumentu (design.md 4.4).
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_scopes: str = "openid profile email groups"
    oidc_email_claim: str = "email"
    oidc_name_claim: str = "name"
    oidc_job_title_claim: str = "job_title"
    oidc_role_claim: str = "groups"
    oidc_admin_role_value: str = "regina-admins"

    # --- Domény evidence ---
    # Útvary jsou uzavřený výčet v konfiguraci, ne editovatelný registr.
    departments_raw: str = Field(
        default="Finance,HR,IT Ops,Risk,Marketing,Provoz",
        alias="DEPARTMENTS",
    )

    # --- Retence (R9.2) ---
    retention_audit_log_days: int = 365
    retention_decommissioned_app_days: int = 730
    retention_interval_hours: int = 24
    retention_enabled: bool = True

    # --- Provoz ---
    log_level: str = "INFO"
    seed_on_start: bool = True

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.strip().upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL musí být jedna z hodnot: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("oidc_issuer", "base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def departments(self) -> tuple[str, ...]:
        """Útvary jako uspořádaná n-tice.

        Čte se z jedné proměnné oddělené čárkou, protože zápis seznamu do `.env`
        v podobě JSON je pro člověka nepohodlný a snadno se rozbije.
        """
        items = [part.strip() for part in self.departments_raw.split(",")]
        return tuple(item for item in items if item)

    @property
    def oidc_scope_list(self) -> list[str]:
        return [scope for scope in self.oidc_scopes.split() if scope]

    @property
    def oidc_redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"

    @property
    def oidc_discovery_url(self) -> str:
        return f"{self.oidc_issuer}/.well-known/openid-configuration"


class ConfigurationError(RuntimeError):
    """Konfigurace je neúplná nebo neplatná."""


def _format_validation_error(error: ValidationError) -> str:
    lines = ["Neplatná konfigurace. Zkontroluj proměnné prostředí nebo soubor .env:"]
    for issue in error.errors():
        location = ".".join(str(part) for part in issue["loc"]) or "(neznámé)"
        lines.append(f"  - {location.upper()}: {issue['msg']}")
    lines.append("Vzor všech proměnných je v .env.example.")
    return "\n".join(lines)


def build_settings(env_file: str | None = ".env") -> Settings:
    """Sestaví nastavení, nebo vyhodí `ConfigurationError` s čitelnou zprávou.

    Parametr `env_file` existuje kvůli testovatelnosti: s hodnotou `None` se
    soubor `.env` ignoruje, takže testy skutečně ověřují chování při chybějící
    proměnné a ne obsah lokálního `.env`.
    """
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as error:
        raise ConfigurationError(_format_validation_error(error)) from error


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Načte nastavení pro běh aplikace.

    Selhání při startu je záměr: chybějící tajemství nebo připojení k databázi
    se má projevit okamžitě, ne až prvním požadavkem uživatele.
    """
    return build_settings()
