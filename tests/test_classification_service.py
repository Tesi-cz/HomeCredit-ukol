"""Jádro zápisu klasifikace (úkol 13.1, R6.1, R6.2, R7.4).

Bez živé databáze: ověřujeme logiku jediného zapisovače proti falešné session,
která jen sbírá přidané objekty. Klíčová tvrzení úkolu 13.1:

- po zápisu se ``applications.classification`` rovná klasifikaci právě
  zapsaného (a tím nejnovějšího) řádku logu — transakční invariant
  (database.md 4, R6.2);
- řádek logu drží předchozí hodnotu, novou hodnotu, zdroj, aktéra;
- auditní akce se odvíjí od zdroje: HUMAN → CLASSIFICATION_SET,
  ADMIN_OVERRIDE → CLASSIFICATION_OVERRIDDEN;
- ADMIN_OVERRIDE s prázdným/jen bílým důvodem je odmítnut ještě v aplikaci.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from regina.db.models.audit_log import AuditLog
from regina.db.models.classification_log import ClassificationLog
from regina.domain.enums import (
    AuditAction,
    Classification,
    ClassificationSource,
    Role,
)
from regina.services.classification import (
    ClassificationPermissionError,
    override_classification,
    set_classification,
    write_classification,
)


class FakeSession:
    """Minimální náhrada session — jen posbírá přidané ORM objekty.

    Funkce ``write_classification`` do session pouze ``add``uje a necommituje
    (design.md 6.3), takže tohle stačí k ověření její logiky bez databáze.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


@dataclass
class FakeApplication:
    """Náhrada záznamu aplikace — nese jen to, čeho se zapisovač dotýká."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    classification: str | None = None


@dataclass(frozen=True)
class FakeActor:
    """Aktér ve tvaru ``AuditActor`` (``id``, ``email``, ``name``) i ``rules.Actor``.

    Nese i ``role``, aby prošel politikou přepisu z úkolu 13.2
    (``rules.can_override_classification`` čte ``actor.role``). Výchozí je
    Admin — testy běžného uživatele si roli přenastaví na ``Role.USER``.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    email: str = "spravce@regina.local"
    name: str = "Jana Nováková"
    role: Role = Role.ADMIN


def _logs(session: FakeSession) -> list[ClassificationLog]:
    return [obj for obj in session.added if isinstance(obj, ClassificationLog)]


def _audits(session: FakeSession) -> list[AuditLog]:
    return [obj for obj in session.added if isinstance(obj, AuditLog)]


def test_human_write_sets_column_and_writes_log_row() -> None:
    """HUMAN zápis přidá řádek logu a nastaví sloupec na novou hodnotu (R6.1)."""
    session = FakeSession()
    app = FakeApplication(classification=None)
    actor = FakeActor()

    entry = write_classification(
        session,
        app,
        Classification.MEDIUM,
        actor,
        ClassificationSource.HUMAN,
    )

    logs = _logs(session)
    assert len(logs) == 1
    assert logs[0] is entry
    assert entry.classification == "MEDIUM"
    assert entry.previous_classification is None  # bylo neklasifikováno
    assert entry.source == "HUMAN"
    assert entry.reason is None
    assert entry.actor_user_id == actor.id
    assert entry.application_id == app.id
    # Denormalizovaný sloupec = nová hodnota.
    assert app.classification == "MEDIUM"


def test_invariant_column_equals_latest_log_row_after_write() -> None:
    """Po zápisu se sloupec rovná klasifikaci posledního zapsaného řádku (R6.2)."""
    session = FakeSession()
    app = FakeApplication(classification="SMALL")
    actor = FakeActor()

    entry = write_classification(
        session,
        app,
        Classification.LARGE,
        actor,
        ClassificationSource.HUMAN,
    )

    # Poslední (a jediný) zapsaný řádek logu je právě `entry`; sloupec mu odpovídá.
    latest = _logs(session)[-1]
    assert latest is entry
    assert app.classification == latest.classification == "LARGE"
    # Předchozí hodnota se zachytila ze sloupce PŘED změnou.
    assert entry.previous_classification == "SMALL"


def test_human_source_writes_classification_set_audit() -> None:
    """HUMAN zdroj zapíše auditní akci CLASSIFICATION_SET (R6.9)."""
    session = FakeSession()
    write_classification(
        session,
        FakeApplication(),
        Classification.SMALL,
        FakeActor(),
        ClassificationSource.HUMAN,
    )
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.CLASSIFICATION_SET)


def test_admin_override_writes_overridden_audit_and_stores_reason() -> None:
    """ADMIN_OVERRIDE zapíše CLASSIFICATION_OVERRIDDEN a uloží důvod (R7.4, R7.7)."""
    session = FakeSession()
    app = FakeApplication(classification="MEDIUM")
    reason = "Zpracovává platební údaje, riziko odpovídá velké aplikaci."

    entry = write_classification(
        session,
        app,
        Classification.LARGE,
        FakeActor(),
        ClassificationSource.ADMIN_OVERRIDE,
        reason=reason,
    )

    assert entry.source == "ADMIN_OVERRIDE"
    assert entry.reason == reason
    assert entry.previous_classification == "MEDIUM"
    assert app.classification == "LARGE"

    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.CLASSIFICATION_OVERRIDDEN)


def test_admin_override_trims_reason_before_storing() -> None:
    """Důvod se před uložením ořízne o okrajové mezery."""
    session = FakeSession()
    entry = write_classification(
        session,
        FakeApplication(),
        Classification.LARGE,
        FakeActor(),
        ClassificationSource.ADMIN_OVERRIDE,
        reason="   Významný dopad na provoz.   ",
    )
    assert entry.reason == "Významný dopad na provoz."


def test_human_source_never_stores_reason() -> None:
    """U jiného zdroje než ADMIN_OVERRIDE se důvod neukládá (database.md 5)."""
    session = FakeSession()
    entry = write_classification(
        session,
        FakeApplication(),
        Classification.SMALL,
        FakeActor(),
        ClassificationSource.HUMAN,
        reason="tenhle důvod se zahodí",
    )
    assert entry.reason is None


@pytest.mark.parametrize("bad_reason", [None, "", "   ", "\t\n"])
def test_admin_override_without_reason_is_rejected(bad_reason: str | None) -> None:
    """ADMIN_OVERRIDE s prázdným/jen bílým důvodem je odmítnut v aplikaci (R7.2).

    Rychlá pojistka před databázovým CHECK constraintem — nesmí se zapsat ani
    řádek logu, ani se změnit sloupec.
    """
    session = FakeSession()
    app = FakeApplication(classification="SMALL")

    with pytest.raises(ValueError):
        write_classification(
            session,
            app,
            Classification.LARGE,
            FakeActor(),
            ClassificationSource.ADMIN_OVERRIDE,
            reason=bad_reason,
        )

    # Fail fast: nic se nepřidalo a sloupec zůstal beze změny.
    assert session.added == []
    assert app.classification == "SMALL"


# -- Politika přepisu a běžného zápisu (úkol 13.2, R6.3, R7) --------------


def test_set_classification_uses_human_source_without_reason() -> None:
    """set_classification zapíše HUMAN a nevyžaduje důvod (R6.3)."""
    session = FakeSession()
    app = FakeApplication(classification=None)
    actor = FakeActor(role=Role.USER)  # člen trojice, běžný zápis

    entry = set_classification(session, app, actor, Classification.SMALL)

    assert entry.source == "HUMAN"
    assert entry.reason is None
    assert app.classification == "SMALL"
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.CLASSIFICATION_SET)


def test_admin_override_via_entry_point_writes_log_audit_and_column() -> None:
    """override_classification (Admin) zapíše log s předchozí/novou hodnotou,
    důvodem a aktérem, audit CLASSIFICATION_OVERRIDDEN a nastaví sloupec (R7.4,
    R7.5, R7.7)."""
    session = FakeSession()
    app = FakeApplication(classification="MEDIUM")
    admin = FakeActor(role=Role.ADMIN)
    reason = "Zpracovává platební údaje, riziko odpovídá velké aplikaci."

    entry = override_classification(session, app, admin, Classification.LARGE, reason)

    # Log zachytí předchozí, novou hodnotu, důvod a aktéra (R7.5).
    assert entry.source == str(ClassificationSource.ADMIN_OVERRIDE)
    assert entry.previous_classification == "MEDIUM"
    assert entry.classification == "LARGE"
    assert entry.reason == reason
    assert entry.actor_user_id == admin.id
    # Invariant: sloupec = poslední řádek logu.
    assert app.classification == "LARGE"
    # Audit přepisu (R7.7).
    audits = _audits(session)
    assert len(audits) == 1
    assert audits[0].action == str(AuditAction.CLASSIFICATION_OVERRIDDEN)


def test_override_rejected_for_user_role_by_service() -> None:
    """Přepis od role User odmítne služba sama, nezávisle na HTTP guardu (R7.1, R7.6).

    Obrana do hloubky: nic se nezapíše a sloupec zůstane beze změny.
    """
    session = FakeSession()
    app = FakeApplication(classification="SMALL")
    user = FakeActor(role=Role.USER)

    with pytest.raises(ClassificationPermissionError):
        override_classification(
            session, app, user, Classification.LARGE, reason="platný důvod"
        )

    assert session.added == []
    assert app.classification == "SMALL"


@pytest.mark.parametrize("bad_reason", ["", "   ", "\t\n"])
def test_override_by_admin_with_empty_reason_is_rejected(bad_reason: str) -> None:
    """Přepis Adminem s prázdným/jen bílým důvodem je odmítnut (R7.2, R7.3).

    Kontrola oprávnění projde (Admin), padne až povinný důvod ve
    ``write_classification``; nic se nezapíše.
    """
    session = FakeSession()
    app = FakeApplication(classification="SMALL")
    admin = FakeActor(role=Role.ADMIN)

    with pytest.raises(ValueError):
        override_classification(
            session, app, admin, Classification.LARGE, reason=bad_reason
        )

    assert session.added == []
    assert app.classification == "SMALL"


def test_permission_checked_before_reason_for_user_with_empty_reason() -> None:
    """Uživatel s prázdným důvodem dostane permission error, ne ValueError.

    Oprávnění se ověřuje jako první (R7.1 má přednost) — přepis se odmítne
    dřív, než se vůbec řeší důvod.
    """
    session = FakeSession()
    user = FakeActor(role=Role.USER)

    with pytest.raises(ClassificationPermissionError):
        override_classification(
            session, FakeApplication(), user, Classification.LARGE, reason=""
        )
