"""Sestavení CSV z registru a auditu (úkol 18.1, R10.1/R10.2/R10.5).

Ověřuje jádro exportní služby bez živé databáze: repozitářní dotazy
(`list_applications`, `list_audit_entries`) a dohledání jmen (`session.execute`)
se přepíší, takže se testuje čistě skládání CSV z předaných řádků.

Co se ověřuje:
- české hlavičky sloupců (R10.5),
- výčty (stav, klasifikace, akce, typ objektu) jako **české popisky**, nikdy
  strojový kód (R10.5, R13.11),
- záznam bez klasifikace → „Neklasifikováno",
- osoby odpovědné trojice jménem; u auditu aktér ze snapshotu (R8.3),
- kódování UTF-8 s BOM (rozhodnutí služby, aby Excel zobrazil diakritiku),
- změněná pole auditu jen jako názvy (R8.6).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone

import pytest

from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.domain.enums import AuditAction, LifecycleState
from regina.repositories.applications import ListResult
from regina.repositories.audit import AuditListResult
from regina.services import export as export_service

_BOM = "\ufeff"


# --- Tovární funkce záznamů ------------------------------------------------


def _application(
    *,
    name: str,
    classification: str | None,
    owner_id: uuid.UUID,
    deputy_id: uuid.UUID | None,
    tech_id: uuid.UUID,
) -> Application:
    app = Application(
        name=name,
        description="Popis " + name,
        department="Finance",
        lifecycle_state=str(LifecycleState.IN_PRODUCTION),
        owner_user_id=owner_id,
        deputy_user_id=deputy_id,
        tech_admin_user_id=tech_id,
        ai_model="gpt-4o",
        classification=classification,
    )
    app.id = uuid.uuid4()
    return app


def _audit_entry() -> AuditLog:
    entry = AuditLog(
        actor_user_id=uuid.uuid4(),
        actor_email="anna.tvurce@regina.local",
        actor_display_name="Anna Tvůrce",
        action=str(AuditAction.APP_CREATED),
        entity_type="APPLICATION",
        entity_id=uuid.uuid4(),
        summary="Vytvoření záznamu aplikace.",
        changed_fields=["name", "department"],
    )
    entry.id = 7
    entry.occurred_at = datetime(2024, 6, 1, 12, 30, tzinfo=timezone.utc)
    return entry


class _NamesSession:
    """Falešná session: `execute(select(id, name))` vrátí předané dvojice."""

    def __init__(self, rows: list[tuple[uuid.UUID, str]]) -> None:
        self._rows = rows

    def execute(self, _stmt):  # noqa: ANN001 - jen pro test
        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return _Result(self._rows)


def _decode(body: bytes) -> tuple[str, list[list[str]]]:
    """Rozloží CSV bajty na (text, řádky) a ověří, že jsou dekódovatelné UTF-8."""
    text = body.decode("utf-8")
    # Řádky bez BOM pro parsování obsahu.
    without_bom = text[len(_BOM):] if text.startswith(_BOM) else text
    rows = list(csv.reader(io.StringIO(without_bom)))
    return text, rows


# --- Export registru -------------------------------------------------------


@pytest.fixture
def owner_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def tech_id() -> uuid.UUID:
    return uuid.uuid4()


def test_registry_csv_has_czech_headers_values_and_bom(monkeypatch, owner_id, tech_id) -> None:
    """Registr: české hlavičky, popisky výčtů, jména osob, UTF-8 + BOM."""
    app = _application(
        name="Portál",
        classification="LARGE",
        owner_id=owner_id,
        deputy_id=None,
        tech_id=tech_id,
    )

    monkeypatch.setattr(
        export_service,
        "list_applications",
        lambda session, filters: ListResult(items=[app], total=1),
    )
    names_session = _NamesSession(
        [(owner_id, "Jan Vlastník"), (tech_id, "Petr Správce")]
    )

    filename, body = export_service.export_registry_csv(names_session)

    assert filename.endswith(".csv")
    # UTF-8 s BOM (rozhodnutí služby kvůli Excelu).
    assert body.startswith(_BOM.encode("utf-8"))

    text, rows = _decode(body)
    header, first = rows[0], rows[1]

    # České hlavičky (R10.5).
    assert header == list(export_service.REGISTRY_HEADERS)
    assert "Název" in header
    assert "Klasifikace" in header

    # Hodnoty: stav a klasifikace jako český popisek (R10.5, R13.11).
    assert "Produkce" in first  # stav IN_PRODUCTION
    assert "VELKÁ" in first  # klasifikace LARGE
    assert "IN_PRODUCTION" not in text  # žádný strojový kód
    assert "LARGE" not in text

    # Osoby jménem; zástupce prázdný (bez zástupce).
    assert "Jan Vlastník" in first
    assert "Petr Správce" in first


def test_registry_csv_unclassified_shows_czech_placeholder(monkeypatch, owner_id, tech_id) -> None:
    """Záznam bez klasifikace → „Neklasifikováno", ne prázdno ani kód (R2.7)."""
    app = _application(
        name="Bez klasifikace",
        classification=None,
        owner_id=owner_id,
        deputy_id=None,
        tech_id=tech_id,
    )
    monkeypatch.setattr(
        export_service,
        "list_applications",
        lambda session, filters: ListResult(items=[app], total=1),
    )
    names_session = _NamesSession([(owner_id, "Jan"), (tech_id, "Petr")])

    _filename, body = export_service.export_registry_csv(names_session)
    _text, rows = _decode(body)

    assert "Neklasifikováno" in rows[1]


# --- Export auditu ---------------------------------------------------------


def test_audit_csv_has_czech_headers_labels_and_snapshot(monkeypatch) -> None:
    """Audit: české hlavičky, popisek akce, aktér ze snapshotu, čas, BOM."""
    entry = _audit_entry()
    monkeypatch.setattr(
        export_service,
        "list_audit_entries",
        lambda session, filters: AuditListResult(items=[entry], total=1),
    )

    filename, body = export_service.export_audit_csv(object())

    assert filename.endswith(".csv")
    assert body.startswith(_BOM.encode("utf-8"))

    text, rows = _decode(body)
    header, first = rows[0], rows[1]

    # České hlavičky (R10.5).
    assert header == list(export_service.AUDIT_HEADERS)
    assert "Čas" in header
    assert "Změněná pole" in header

    # Akce jako český popisek, ne strojový kód (R10.5, R13.11).
    assert "Vytvoření záznamu" in first
    assert "APP_CREATED" not in text

    # Typ objektu český popisek.
    assert any("Aplikace" in cell for cell in first)

    # Čas DD.MM.YYYY HH:MM (R13.3).
    assert "01.06.2024 12:30" in first

    # Aktér a e-mail ze snapshotu (R8.3).
    assert "Anna Tvůrce" in first
    assert "anna.tvurce@regina.local" in first

    # Změněná pole jen jako názvy (R8.6).
    assert any("name" in cell and "department" in cell for cell in first)
