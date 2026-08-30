"""Testy konfigurace.

Ověřují dvě tvrzení z návrhu: chybějící povinná hodnota shodí start s čitelnou
zprávou, a útvary se čtou z jedné proměnné oddělené čárkou.
"""

from __future__ import annotations

import pytest

from regina.config import ConfigurationError, Settings, build_settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+psycopg://regina:secret@db:5432/regina",
    "SESSION_SECRET": "x" * 32,
    "OIDC_ISSUER": "http://dex:5556/dex",
    "OIDC_CLIENT_ID": "regina",
    "OIDC_CLIENT_SECRET": "client-secret",
}


def _apply_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for key in (*REQUIRED_ENV, "DEPARTMENTS", "LOG_LEVEL", "BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_complete_configuration_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _apply_env(monkeypatch, REQUIRED_ENV)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "REGINA"
    assert settings.oidc_redirect_uri.endswith("/auth/callback")
    assert settings.oidc_discovery_url.endswith("/.well-known/openid-configuration")


@pytest.mark.parametrize("missing", sorted(REQUIRED_ENV))
def test_missing_required_value_is_reported(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    """Chybějící povinná hodnota musí být pojmenovaná ve zprávě.

    `env_file=None` je podstatné: bez toho by hodnotu dodal lokální `.env`
    a test by neověřoval nic.
    """
    partial = {key: value for key, value in REQUIRED_ENV.items() if key != missing}
    _apply_env(monkeypatch, partial)

    with pytest.raises(ConfigurationError) as error:
        build_settings(env_file=None)

    message = str(error.value)
    assert missing in message
    assert ".env.example" in message


def test_short_session_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Krátké tajemství pro podpis session je odmítnuto."""
    _apply_env(monkeypatch, {**REQUIRED_ENV, "SESSION_SECRET": "prilis-kratke"})

    with pytest.raises(ConfigurationError) as error:
        build_settings(env_file=None)

    assert "SESSION_SECRET" in str(error.value)


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _apply_env(monkeypatch, {**REQUIRED_ENV, "LOG_LEVEL": "CHATTY"})

    with pytest.raises(ConfigurationError) as error:
        build_settings(env_file=None)

    assert "LOG_LEVEL" in str(error.value)


def test_departments_are_parsed_from_comma_separated_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _apply_env(
        monkeypatch,
        {**REQUIRED_ENV, "DEPARTMENTS": "Finance, HR ,, IT Ops "},
    )

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.departments == ("Finance", "HR", "IT Ops")


def test_trailing_slash_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Discovery URL nesmí obsahovat dvojité lomítko."""
    _apply_env(
        monkeypatch,
        {**REQUIRED_ENV, "OIDC_ISSUER": "http://dex:5556/dex/", "BASE_URL": "http://x/"},
    )

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.oidc_discovery_url == "http://dex:5556/dex/.well-known/openid-configuration"
    assert settings.oidc_redirect_uri == "http://x/auth/callback"
