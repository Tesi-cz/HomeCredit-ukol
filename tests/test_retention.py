"""Retenční rutina (úkol 19.1, R9).

Ověřuje jádro rutiny bez skutečné databáze: hranice se počítají z konfigurace
a z `now`, mazání auditu prochází výhradně přes `audit_retention_context`
a smazání aplikace míří jen na vyřazené záznamy za hranicí. Skutečné kaskády
`ON DELETE CASCADE` a přežití auditu vynucuje databáze; to je předmětem
integračních testů retence (úkol 19.3).

Náhrada session zaznamenává, zda `DELETE` nad `audit_log` proběhl uvnitř
retenčního kontextu — to je bezpečnostní tvrzení úkolu 19.1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.services import retention


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _RecordingSession:
    """Zaznamená spuštěné `DELETE` a stav retenčního příznaku v okamžiku běhu."""

    def __init__(self) -> None:
        self.info: dict[str, object] = {}
        self.executed: list[tuple[object, bool]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, statement: object) -> _FakeResult:
        retention_flag = bool(self.info.get("regina.audit_retention_delete", False))
        self.executed.append((statement, retention_flag))
        # Dvě různé počty, ať test rozezná obě kategorie.
        table = getattr(statement, "table", None)
        name = getattr(table, "name", "")
        return _FakeResult(3 if name == "audit_log" else 2)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _install_fake_session(monkeypatch) -> _RecordingSession:
    session = _RecordingSession()

    from contextlib import contextmanager

    @contextmanager
    def _scope():
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(retention.db_session, "session_scope", _scope)
    return session


def test_computes_boundaries_from_now_and_configured_days(settings, monkeypatch) -> None:
    """Hranice = now - počet dní z konfigurace pro obě kategorie (R9.2, R9.4)."""
    _install_fake_session(monkeypatch)
    now = datetime(2025, 1, 1, tzinfo=UTC)

    result = retention.run_retention_once(settings, now=now)

    assert result.audit_cutoff == now - timedelta(days=settings.retention_audit_log_days)
    assert result.apps_cutoff == now - timedelta(
        days=settings.retention_decommissioned_app_days
    )


def test_audit_delete_runs_inside_retention_context(settings, monkeypatch) -> None:
    """`DELETE` nad audit_log proběhne jen uvnitř retenčního kontextu (R8.5)."""
    session = _install_fake_session(monkeypatch)

    retention.run_retention_once(settings, now=datetime(2025, 1, 1, tzinfo=UTC))

    # Najdi příkaz cílící na audit_log a ověř, že běžel s aktivním příznakem.
    audit_runs = [
        flag
        for statement, flag in session.executed
        if getattr(getattr(statement, "table", None), "name", "") == AuditLog.__tablename__
    ]
    assert audit_runs == [True]
    # Po opuštění kontextu je příznak zase vypnutý.
    assert session.info.get("regina.audit_retention_delete", False) is False


def test_app_delete_runs_outside_retention_context(settings, monkeypatch) -> None:
    """Mazání aplikací s retenčním příznakem nesouvisí — běží mimo kontext."""
    session = _install_fake_session(monkeypatch)

    retention.run_retention_once(settings, now=datetime(2025, 1, 1, tzinfo=UTC))

    app_runs = [
        flag
        for statement, flag in session.executed
        if getattr(getattr(statement, "table", None), "name", "")
        == Application.__tablename__
    ]
    assert app_runs == [False]


def test_returns_deleted_counts_and_commits(settings, monkeypatch) -> None:
    """Rutina vrací počty smazaných řádků a potvrdí transakci."""
    session = _install_fake_session(monkeypatch)

    result = retention.run_retention_once(settings, now=datetime(2025, 1, 1, tzinfo=UTC))

    assert result.audit_deleted == 3
    assert result.apps_deleted == 2
    assert session.committed is True


def test_logs_category_cutoff_and_count_per_category(settings, monkeypatch, caplog) -> None:
    """Každý běh loguje kategorii, hranici a počet smazaných (R9.5).

    Očekáváme jeden strukturovaný záznam na kategorii s klíčem události
    `retention.category_completed`, se strojovým klíčem kategorie, hranicí
    v ISO formátu a počtem smazaných řádků.
    """
    _install_fake_session(monkeypatch)
    now = datetime(2025, 1, 1, tzinfo=UTC)

    with caplog.at_level("INFO", logger="regina.retention"):
        retention.run_retention_once(settings, now=now)

    records = [
        r for r in caplog.records if getattr(r, "event", None) == "retention.category_completed"
    ]
    by_category = {r.category: r for r in records}

    assert set(by_category) == {"audit_log", "decommissioned_applications"}

    audit = by_category["audit_log"]
    assert audit.deleted == 3
    assert audit.cutoff == (
        now - timedelta(days=settings.retention_audit_log_days)
    ).isoformat()

    apps = by_category["decommissioned_applications"]
    assert apps.deleted == 2
    assert apps.cutoff == (
        now - timedelta(days=settings.retention_decommissioned_app_days)
    ).isoformat()


def test_logs_even_when_nothing_deleted(settings, monkeypatch, caplog) -> None:
    """I běh, který nic nesmaže, se zaloguje — důkaz, že retence proběhla."""

    class _ZeroSession(_RecordingSession):
        def execute(self, statement: object) -> _FakeResult:
            super().execute(statement)
            return _FakeResult(0)

    session = _ZeroSession()

    from contextlib import contextmanager

    @contextmanager
    def _scope():
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(retention.db_session, "session_scope", _scope)

    with caplog.at_level("INFO", logger="regina.retention"):
        retention.run_retention_once(settings, now=datetime(2025, 1, 1, tzinfo=UTC))

    records = [
        r for r in caplog.records if getattr(r, "event", None) == "retention.category_completed"
    ]
    assert len(records) == 2
    assert all(r.deleted == 0 for r in records)


def test_log_contains_no_personal_data(settings, monkeypatch, caplog) -> None:
    """Log nese jen počty a hranice — žádná jména, e-maily ani obsah řádků (R12.10)."""
    _install_fake_session(monkeypatch)

    with caplog.at_level("INFO", logger="regina.retention"):
        retention.run_retention_once(settings, now=datetime(2025, 1, 1, tzinfo=UTC))

    records = [
        r for r in caplog.records if getattr(r, "event", None) == "retention.category_completed"
    ]
    allowed_extra = {
        "event",
        "category",
        "category_label",
        "cutoff",
        "deleted",
    }
    for record in records:
        extra_keys = {
            key
            for key in vars(record)
            if key
            not in {
                "name",
                "msg",
                "message",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
            }
        }
        # Jediná doplňková pole záznamu jsou počty, hranice a popisky kategorie.
        assert extra_keys <= allowed_extra
        # Vykreslená zpráva neobsahuje osobní údaje — jen kategorii, hranici, počet.
        assert "@" not in record.getMessage()
