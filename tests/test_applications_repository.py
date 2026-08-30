"""Dotaz na výpis registru (úkol 11.1, R3.2/3.3/3.9/3.10/3.11).

Bez živé databáze: dotazy se sestaví a zkontroluje jejich SQL proti
PostgreSQL dialektu. Tím ověříme klíčová tvrzení dotazu — hlavně výchozí
skrytí vyřazených záznamů a jeho vypnutí při explicitní volbě stavu —
aniž bychom potřebovali připojení k databázi.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from regina.db.models.applications import Application
from regina.domain.enums import Classification, LifecycleState
import uuid

from regina.repositories.applications import (
    ListFilters,
    ListResult,
    _apply_filters,
    _escape_like,
)


def _sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _where_sql(filters: ListFilters) -> str:
    return _sql(_apply_filters(select(Application), filters))


def test_default_list_hides_decommissioned() -> None:
    """Bez zvoleného stavu výpis vylučuje vyřazené záznamy (R3.9)."""
    sql = _where_sql(ListFilters())
    assert "lifecycle_state != 'DECOMMISSIONED'" in sql


def test_explicit_decommissioned_is_honored_exactly() -> None:
    """Zvolený stav DECOMMISSIONED se respektuje; výchozí skrytí se neuplatní."""
    sql = _where_sql(ListFilters(state=LifecycleState.DECOMMISSIONED))
    assert "lifecycle_state = 'DECOMMISSIONED'" in sql
    assert "!= 'DECOMMISSIONED'" not in sql


def test_explicit_other_state_disables_default_hide() -> None:
    """Jakýkoli zvolený stav vypne výchozí skrytí vyřazených."""
    sql = _where_sql(ListFilters(state=LifecycleState.IN_PRODUCTION))
    assert "lifecycle_state = 'IN_PRODUCTION'" in sql
    assert "!= 'DECOMMISSIONED'" not in sql


def test_name_search_is_case_and_accent_insensitive() -> None:
    """Hledání porovnává f_unaccent(lower(name)) LIKE f_unaccent(lower(:q)) (R3.2).

    `f_unaccent` (IMMUTABLE obal nad rozšířením `unaccent`) odstraní diakritiku
    na obou stranách, takže „pre" najde „pře", „prě", „před"; `lower` doplňuje
    necitlivost na velikost písmen.
    """
    sql = _where_sql(ListFilters(query="Portál"))
    assert "f_unaccent(lower(applications.name)) LIKE f_unaccent(lower(" in sql


def test_blank_query_does_not_filter_name() -> None:
    """Prázdný nebo jen-mezerový výraz = bez filtru názvu."""
    assert "LIKE" not in _where_sql(ListFilters(query="   ")).upper()


def test_like_wildcards_are_escaped() -> None:
    """Zástupné znaky ve vstupu nesmí fungovat jako žolík."""
    assert _escape_like("50%_x\\y") == "50\\%\\_x\\\\y"


def test_filters_combine_by_equality() -> None:
    """Útvar, klasifikace a stav se kombinují rovností (R3.3)."""
    sql = _where_sql(
        ListFilters(
            department="Finance",
            classification=Classification.LARGE,
            state=LifecycleState.TESTING,
        )
    )
    assert "department = 'Finance'" in sql
    assert "classification = 'LARGE'" in sql
    assert "lifecycle_state = 'TESTING'" in sql


def test_unclassified_only_filters_null_and_overrides_classification() -> None:
    """„Neklasifikováno" = classification IS NULL a přebije classification."""
    sql = _where_sql(
        ListFilters(unclassified_only=True, classification=Classification.SMALL)
    )
    assert "classification IS NULL" in sql
    assert "classification = 'SMALL'" not in sql


def test_count_respects_filters_without_pagination() -> None:
    """Celkový počet je nad filtry, ne nad stránkou (R3.5/3.11)."""
    stmt = _apply_filters(
        select(func.count()).select_from(Application),
        ListFilters(department="Finance"),
    )
    sql = _sql(stmt)
    assert "count(*)" in sql.lower()
    assert "department = 'Finance'" in sql
    assert "LIMIT" not in sql.upper()


def test_order_and_pagination_shape() -> None:
    """Řazení podle lower(name), stabilní id, LIMIT/OFFSET."""
    stmt = (
        _apply_filters(select(Application), ListFilters())
        .order_by(func.lower(Application.name).asc(), Application.id)
        .limit(20)
        .offset(40)
    )
    sql = _sql(stmt)
    assert "ORDER BY lower(applications.name) ASC" in sql
    assert "LIMIT 20" in sql
    assert "OFFSET 40" in sql


def test_list_result_defaults_empty() -> None:
    result = ListResult()
    assert result.items == []
    assert result.total == 0


# --- „Moje aplikace" — členství v odpovědné trojici podle identity (úkol 12.1) ---


def test_trio_member_matches_owner_deputy_or_tech_admin_by_id() -> None:
    """Filtr trojice hledá shodu identity s vlastníkem, zástupcem NEBO správcem (R3.10, R4.2)."""
    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    sql = _where_sql(ListFilters(trio_member_id=user_id))
    literal = f"'{user_id}'"
    assert f"applications.owner_user_id = {literal}" in sql
    assert f"applications.deputy_user_id = {literal}" in sql
    assert f"applications.tech_admin_user_id = {literal}" in sql
    # Členství je OR přes tři sloupce.
    assert " OR " in sql


def test_trio_filter_matches_by_id_never_by_name() -> None:
    """Členství se rozhoduje jen podle identifikátorů osob, ne podle jmen (R4.2)."""
    user_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    sql = _where_sql(ListFilters(trio_member_id=user_id))
    # Bez hledání podle názvu se do WHERE nedostane žádné porovnání na `name`;
    # trojice se řeší výhradně přes `*_user_id` sloupce.
    where_clause = sql.lower().split("where", 1)[1]
    assert "applications.name" not in where_clause


def test_trio_filter_uses_equality_so_null_deputy_never_matches() -> None:
    """NULL deputy_user_id se s identitou nikdy neshodne — rovnost v SQL neplatí pro NULL."""
    user_id = uuid.UUID("33333333-3333-3333-3333-333333333333")
    sql = _where_sql(ListFilters(trio_member_id=user_id))
    # Rovnostní porovnání (`= :id`), ne `IS NULL`/`IS NOT NULL` na sloupcích trojice.
    assert "deputy_user_id IS" not in sql
    assert f"applications.deputy_user_id = '{user_id}'" in sql


def test_trio_filter_none_is_noop() -> None:
    """Bez trio_member_id se nepřidá žádná podmínka na trojici (chování 11.1 beze změny)."""
    where_clause = _where_sql(ListFilters()).lower().split("where", 1)[1]
    assert "owner_user_id" not in where_clause
    assert "deputy_user_id" not in where_clause
    assert "tech_admin_user_id" not in where_clause


def test_trio_filter_hides_decommissioned_by_default() -> None:
    """„Moje aplikace" drží stejné výchozí skrytí vyřazených jako registr (R3.9)."""
    user_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
    sql = _where_sql(ListFilters(trio_member_id=user_id))
    assert "lifecycle_state != 'DECOMMISSIONED'" in sql


def test_trio_filter_combines_with_search() -> None:
    """Trojice se kombinuje s hledáním podle názvu (hero „Moje aplikace" má vyhledávání)."""
    user_id = uuid.UUID("55555555-5555-5555-5555-555555555555")
    sql = _where_sql(ListFilters(trio_member_id=user_id, query="Portál"))
    assert "f_unaccent(lower(applications.name)) LIKE f_unaccent(lower(" in sql
    assert f"applications.owner_user_id = '{user_id}'" in sql


def test_count_respects_trio_filter() -> None:
    """Celkový počet pro „Moje aplikace" respektuje filtr trojice (R3.5)."""
    user_id = uuid.UUID("66666666-6666-6666-6666-666666666666")
    stmt = _apply_filters(
        select(func.count()).select_from(Application),
        ListFilters(trio_member_id=user_id),
    )
    sql = _sql(stmt)
    assert "count(*)" in sql.lower()
    assert f"applications.owner_user_id = '{user_id}'" in sql
    assert "LIMIT" not in sql.upper()
