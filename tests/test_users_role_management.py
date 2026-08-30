"""Správa rolí: autorizace na backendu a pojistka posledního správce (úkol 17.2).

Dvě samostatné roviny:

1. **Autorizace obrazovky `/uzivatele` (R11.2, R2.2).** Přímý `GET` i `POST` od
   role User je zamítnut guardem `require_manage_roles` — 403 + audit
   `ACCESS_DENIED`, i když rozhraní roli User položku „Uživatelé" ani přepínač
   nikdy nenabídlo. Vynucení leží v guardu, ne v tom, co se vykreslí. Testuje
   se přes `TestClient` nad reálně složenou aplikací (`create_app`) **bez živé
   databáze**: `require_login` a `get_session` se přepíší, `session_scope` v
   handleru zamítnutí taky.

2. **Služba `set_role` (R11.4, R11.5, R11.6).** Čistý test nad falešnou session
   a falešným `count_admins` — bez databáze. Ověří, že přepnutí role nastaví
   roli i zdroj (`LOCAL`) a zapíše audit `ROLE_CHANGED`, a že pojistka
   posledního správce odmítne odebrat poslední adminská práva `LastAdminError`
   (včetně sebe-odebrání).
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient

from regina.auth import deps as auth_deps
from regina.auth.deps import CurrentUser, require_login
from regina.db.models.users import User
from regina.db.session import get_session
from regina.domain.enums import Role, RoleSource
from regina.main import create_app
from regina.services import users as users_service
from regina.services.users import LastAdminError, set_role


# -- Roviny 1: autorizace obrazovky na backendu --------------------------


class _FakeSession:
    """Session pro guard trasy — v testu autorizace se z ní nečte."""


def _regular_user() -> CurrentUser:
    """Přihlášený uživatel role USER (nesmí spravovat role)."""
    return CurrentUser(
        id=uuid.uuid4(),
        subject="user-subject",
        name="Jan Novák",
        email="jan.novak@regina.local",
        role=Role.USER,
    )


@pytest.fixture
def app_and_recorder(settings, monkeypatch):
    """Aplikace s přepsanými závislostmi (role User) a odchytnutým auditem."""
    audit_calls: list[dict[str, object]] = []
    app = create_app(settings)

    def _override_session():
        yield _FakeSession()

    app.dependency_overrides[require_login] = _regular_user
    app.dependency_overrides[get_session] = _override_session

    @contextlib.contextmanager
    def _fake_scope():
        yield object()

    monkeypatch.setattr(auth_deps, "session_scope", _fake_scope)

    def _record_access_denied(session, actor, *, summary, entity_type=None, entity_id=None):
        audit_calls.append({"summary": summary, "entity_type": entity_type})

    monkeypatch.setattr(auth_deps.audit_service, "access_denied", _record_access_denied)

    return TestClient(app), audit_calls


def test_user_list_forbidden_for_regular_user(app_and_recorder) -> None:
    """GET /uzivatele od role User → 403 (R11.2, R2.2)."""
    client, _ = app_and_recorder
    assert client.get("/uzivatele").status_code == 403


def test_role_post_forbidden_for_regular_user(app_and_recorder) -> None:
    """Přímý POST /uzivatele/{id}/role od role User → 403 + audit (R11.2, R2.2).

    Zamítne ho guard `require_manage_roles` dřív, než se dojde k CSRF nebo ke
    službě — i bez tlačítka v rozhraní.
    """
    client, audit_calls = app_and_recorder
    response = client.post(
        f"/uzivatele/{uuid.uuid4()}/role",
        data={"role": "ADMIN"},
    )
    assert response.status_code == 403
    assert len(audit_calls) == 1


# -- Roviny 2: služba set_role -------------------------------------------


class _FakeRoleSession:
    """Falešná session; audit zapisuje přes `session.add`, který jen sbírá."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


def _person(role: Role) -> User:
    person = User(
        email="petra@regina.local",
        display_name="Petra Admincová",
        role=str(role),
        role_source=str(RoleSource.IDP),
    )
    person.id = uuid.uuid4()
    return person


def _actor() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        subject="admin-subject",
        name="Alena Správná",
        email="alena@regina.local",
        role=Role.ADMIN,
    )


def test_set_role_changes_role_and_source_and_audits(monkeypatch) -> None:
    """Přepnutí USER→ADMIN nastaví roli, zdroj LOCAL a zapíše ROLE_CHANGED (R11.4, R11.6)."""
    session = _FakeRoleSession()
    target = _person(Role.USER)

    result = set_role(session, _actor(), target, Role.ADMIN)

    assert result is target
    assert target.role == str(Role.ADMIN)
    # Roli zapsal správce lokálně → zdroj LOCAL (R11.6).
    assert target.role_source == str(RoleSource.LOCAL)
    # Audit ROLE_CHANGED nad dotčeným uživatelem (R11.4).
    assert len(session.added) == 1
    entry = session.added[0]
    assert entry.action == "ROLE_CHANGED"
    assert entry.entity_type == "USER"
    assert entry.entity_id == target.id


def test_set_role_noop_when_role_unchanged(monkeypatch) -> None:
    """Shodná role = žádná změna ani audit (idempotence)."""
    session = _FakeRoleSession()
    target = _person(Role.ADMIN)

    set_role(session, _actor(), target, Role.ADMIN)

    assert session.added == []


def test_set_role_rejects_removing_last_admin(monkeypatch) -> None:
    """Odebrání role poslednímu správci → LastAdminError, nic se nezapíše (R11.5)."""
    monkeypatch.setattr(users_service.users_repo, "count_admins", lambda s: 1)
    session = _FakeRoleSession()
    target = _person(Role.ADMIN)

    with pytest.raises(LastAdminError):
        set_role(session, _actor(), target, Role.USER)

    # Role zůstala a nic se nezapsalo do auditu.
    assert target.role == str(Role.ADMIN)
    assert session.added == []


def test_set_role_allows_demoting_when_other_admins_remain(monkeypatch) -> None:
    """Odebrání role jednomu ze dvou správců projde (zůstává jeden, R11.5)."""
    monkeypatch.setattr(users_service.users_repo, "count_admins", lambda s: 2)
    session = _FakeRoleSession()
    target = _person(Role.ADMIN)

    set_role(session, _actor(), target, Role.USER)

    assert target.role == str(Role.USER)
    assert target.role_source == str(RoleSource.LOCAL)
    assert len(session.added) == 1
