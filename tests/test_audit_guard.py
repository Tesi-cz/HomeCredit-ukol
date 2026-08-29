"""Pojistka nemazatelnosti auditu (R8.5, úkol 10.2).

Ověřuje pravidlo, že aplikace nikdy nevydá `UPDATE` ani `DELETE` nad
`audit_log`, s jedinou výjimkou — retenční rutinou (úkol 19.1) přes
`audit_retention_context`.

Test cílí přímo na posluchač `before_flush`. ORM objekty se dají vytvořit i bez
připojené databáze, takže si vystačíme s odlehčenou náhradou session, která
nese jen to, co posluchač čte: `dirty`, `deleted`, `info` a `is_modified`.
Postgresové typy (`JSONB`, `UUID`) tím nemusíme kompilovat pro SQLite.
"""

from __future__ import annotations

import pytest

from regina.db.audit_guard import (
    AuditImmutableError,
    _before_flush,
    audit_retention_context,
)
from regina.db.models.audit_log import AuditLog
from regina.db.models.users import User


class _FakeSession:
    """Nese jen to, co posluchač `before_flush` čte."""

    def __init__(self, *, dirty=(), deleted=(), new=()) -> None:
        self.dirty = set(dirty)
        self.deleted = set(deleted)
        self.new = set(new)
        self.info: dict[str, object] = {}

    def is_modified(self, _obj: object) -> bool:
        # V testu je vše v `dirty` skutečně změněné.
        return True


def _flush(session: _FakeSession) -> None:
    _before_flush(session, None, None)


def test_inserting_audit_log_is_allowed() -> None:
    """Přírůstek je celý smysl auditu — vložení nikdy neblokujeme."""
    session = _FakeSession(new=[AuditLog(action="SIGN_IN")])
    _flush(session)  # nesmí vyhodit


def test_updating_audit_log_is_rejected() -> None:
    """Editace auditního záznamu je programátorská chyba (R8.5)."""
    session = _FakeSession(dirty=[AuditLog(action="SIGN_IN")])
    with pytest.raises(AuditImmutableError):
        _flush(session)


def test_deleting_audit_log_is_rejected_outside_retention() -> None:
    """Mimo retenci nesmí projít žádné mazání auditu (R8.5)."""
    session = _FakeSession(deleted=[AuditLog(action="SIGN_IN")])
    with pytest.raises(AuditImmutableError):
        _flush(session)


def test_deleting_audit_log_is_allowed_within_retention_context() -> None:
    """Retenční rutina (úkol 19.1) je jediná povolená výjimka pro mazání."""
    session = _FakeSession(deleted=[AuditLog(action="SIGN_IN")])
    with audit_retention_context(session):
        _flush(session)  # uvnitř kontextu retence smí mazat


def test_updating_audit_log_is_rejected_even_within_retention_context() -> None:
    """Retence záznamy jen maže; editaci pojistka odmítne i v jejím kontextu."""
    session = _FakeSession(dirty=[AuditLog(action="SIGN_IN")])
    with pytest.raises(AuditImmutableError), audit_retention_context(session):
        _flush(session)


def test_retention_flag_is_cleared_after_context() -> None:
    """Po opuštění bloku už mazání auditu zase neprojde."""
    session = _FakeSession(deleted=[AuditLog(action="SIGN_IN")])
    with audit_retention_context(session):
        pass
    with pytest.raises(AuditImmutableError):
        _flush(session)


def test_retention_flag_is_cleared_even_on_exception() -> None:
    """Výjimka uvnitř bloku nesmí nechat příznak retence viset zapnutý."""
    session = _FakeSession()
    with pytest.raises(RuntimeError), audit_retention_context(session):
        raise RuntimeError("boom")
    session.deleted = {AuditLog(action="SIGN_IN")}
    with pytest.raises(AuditImmutableError):
        _flush(session)


def test_other_tables_are_unaffected_by_update() -> None:
    """Editace jiných tabulek (users) pojistka neřeší."""
    session = _FakeSession(dirty=[User(email="a@b.cz", display_name="A")])
    _flush(session)  # nesmí vyhodit


def test_other_tables_are_unaffected_by_delete() -> None:
    """Mazání jiných tabulek (users) pojistka neřeší."""
    session = _FakeSession(deleted=[User(email="a@b.cz", display_name="A")])
    _flush(session)  # nesmí vyhodit
