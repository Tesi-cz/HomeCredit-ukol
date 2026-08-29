"""Autorizace a stažení exportu CSV (úkol 18.1, R10.1/R10.2/R10.4).

Ověřuje routy `/export/registr` a `/export/audit` bez živé databáze:
závislosti `require_login` a `get_session` se přepíší, exportní služba se
monkeypatchne, takže test projde reálnou routou i guardem `require_export`.

Co se ověřuje:
- export je vyhrazen roli Admin — role User dostane 403 + audit `ACCESS_DENIED`
  i při přímém GET, bez ohledu na to, že jí rozhraní tlačítko neukázalo
  (R10.4, R2.2), vzorem podle `test_edit_route_authorization.py`;
- Admin dostane CSV ke stažení: `text/csv`, `Content-Disposition: attachment`,
  tělo s UTF-8 BOM.
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient

from regina.auth import deps as auth_deps
from regina.auth.deps import CurrentUser, require_login
from regina.db.session import get_session
from regina.domain.enums import Role
from regina.main import create_app
from regina.web.routes import export as export_routes


def _admin_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="admin-subject",
        name="Dáša Správcová",
        email="admin@regina.local",
        role=Role.ADMIN,
    )


def _regular_user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="user-subject",
        name="Jan Novák",
        email="jan.novak@regina.local",
        role=Role.USER,
    )


class _FakeSession:
    """Session bez databáze — export route s ní jen prochází závislostí."""


@pytest.fixture
def make_client(settings, monkeypatch):
    """Sestaví TestClient s přepsanými závislostmi a exportní službou.

    Exportní funkce se monkeypatchnou v namespace routy, aby test nepotřeboval
    databázi a vracel hotové CSV bajty.
    """

    def build(user_factory):
        app = create_app(settings)

        def _override_session():
            yield _FakeSession()

        app.dependency_overrides[require_login] = user_factory
        app.dependency_overrides[get_session] = _override_session

        monkeypatch.setattr(
            export_routes,
            "export_registry_csv",
            lambda session, filters: ("registr-aplikaci.csv", "\ufeffNázev\r\n".encode("utf-8")),
        )
        monkeypatch.setattr(
            export_routes,
            "export_audit_csv",
            lambda session, filters: ("auditni-log.csv", "\ufeffČas\r\n".encode("utf-8")),
        )

        return TestClient(app)

    return build


@pytest.fixture
def audit_recorder(monkeypatch):
    """Odchytí audit ACCESS_DENIED bez zápisu do databáze."""
    calls: list[dict[str, object]] = []

    @contextlib.contextmanager
    def _fake_scope():
        yield object()

    monkeypatch.setattr(auth_deps, "session_scope", _fake_scope)

    def _record(session, actor, *, summary, entity_type=None, entity_id=None):
        calls.append({"actor": actor, "summary": summary})

    monkeypatch.setattr(auth_deps.audit_service, "access_denied", _record)
    return calls


# --- Autorizace (jen Admin, R10.4) -----------------------------------------


def test_registry_export_rejected_for_user(make_client, audit_recorder) -> None:
    """Role User na /export/registr → 403 (R10.4, R2.2)."""
    client = make_client(_regular_user)
    assert client.get("/export/registr").status_code == 403


def test_audit_export_rejected_for_user(make_client, audit_recorder) -> None:
    """Role User na /export/audit → 403 (R10.4, R2.2)."""
    client = make_client(_regular_user)
    assert client.get("/export/audit").status_code == 403


def test_rejected_export_writes_access_denied_audit(make_client, audit_recorder) -> None:
    """Zamítnutý export se zapíše jako ACCESS_DENIED (R2.3)."""
    client = make_client(_regular_user)
    client.get("/export/registr")
    assert len(audit_recorder) == 1


# --- Stažení pro Admina ----------------------------------------------------


def test_admin_downloads_registry_csv(make_client) -> None:
    """Admin dostane CSV ke stažení: text/csv, attachment, BOM (R10.1, R10.5)."""
    client = make_client(_admin_user)

    response = client.get("/export/registr")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "registr-aplikaci.csv" in response.headers["content-disposition"]
    assert response.content.startswith("\ufeff".encode("utf-8"))


def test_admin_downloads_audit_csv(make_client) -> None:
    """Admin dostane auditní CSV ke stažení (R10.2, R10.5)."""
    client = make_client(_admin_user)

    response = client.get("/export/audit")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "auditni-log.csv" in response.headers["content-disposition"]
    assert response.content.startswith("\ufeff".encode("utf-8"))
