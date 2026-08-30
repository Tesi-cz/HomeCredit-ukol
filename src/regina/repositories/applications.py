"""Repozitář aplikací — dotaz pro tabulkový výpis registru (design.md 6.2).

Filtrování, vyhledávání, řazení a stránkování se skládají na **jednom místě**
a provádí je databáze, ne aplikace v paměti (R3.6). Route (úkol 11.2) sem
předá parametry z URL, dostane zpět jednu stránku záznamů plus celkový počet
odpovídající filtrům a z celkového počtu si přes `web/pagination.paginate()`
sestaví text „Zobrazeno X–Y z N záznamů" (R3.5, R3.10, R3.11).

Klíčová pravidla dotazu:

- **Výchozí výpis skrývá vyřazené** *(R3.9)*. Když volající neurčí explicitně
  filtr stavu, dotaz vylučuje `lifecycle_state = 'DECOMMISSIONED'`. To využívá
  částečný index `ix_applications_active`. Jakmile volající stav zvolí — a to
  i `DECOMMISSIONED` — respektuje se přesně a výchozí skrytí se **neuplatní**.
  Rozlišení „nezvoleno" vs. „zvoleno DECOMMISSIONED" nese `None` vs. konkrétní
  hodnota v `state`; kvůli tomu je to samostatný parametr, ne řetězec v URL.
- **Hledání bez ohledu na velikost písmen a diakritiku** *(R3.2)*.
  `f_unaccent(lower(name)) LIKE f_unaccent(lower(:q))` nad funkcionálním indexem
  `ix_applications_unaccent_lower_name`. `f_unaccent` je IMMUTABLE obal nad
  rozšířením `unaccent` (migrace `a1b2c3d4e5f6`), který odstraní diakritiku —
  takže „pre" najde „pře", „prě", „před". Zástupné znaky ve vyhledávaném výrazu
  (`%`, `_`, zpětné lomítko) se escapují, aby uživatelský vstup nefungoval jako
  žolík. Prázdný nebo jen-mezerový výraz = bez filtru názvu.
- **Filtry** *(R3.3)* jsou rovnosti na `department`, `classification`,
  `lifecycle_state`, kombinovatelné. `classification=None` neznamená filtr;
  pro záznamy bez klasifikace („Neklasifikováno") existuje výslovný přepínač
  `unclassified_only`.
- **Řazení podle názvu** *(R3.4)* přes `lower(name)`, aby bylo nezávislé na
  velikosti písmen. Řadí se podle **napevno daného sloupce**, nikdy podle názvu
  z parametru URL (design.md 6.2 — obrana proti SQL injection).
- **Stránkování** *(R3.5)* přes `LIMIT`/`OFFSET`; celkový počet přes `COUNT`
  nad **stejnými filtry, ale před stránkováním**, takže „z N" sedí na filtry,
  ne na velikost stránky.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from regina.db.models.applications import Application
from regina.domain.enums import Classification, LifecycleState

# Escapovací znak pro LIKE. `name` uživatele může obsahovat `%` nebo `_`, které
# jsou v LIKE žolíky; bez escapování by hledání „50 %" našlo cokoli. Escapujeme
# i samotný escapovací znak.
_LIKE_ESCAPE = "\\"


def _escape_like(term: str) -> str:
    """Zneškodní zástupné znaky LIKE ve vyhledávaném výrazu."""
    return (
        term.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", f"{_LIKE_ESCAPE}%")
        .replace("_", f"{_LIKE_ESCAPE}_")
    )


@dataclass(frozen=True)
class ListFilters:
    """Parametry výpisu registru, jak je route sesbírá z URL.

    Všechna pole jsou volitelná a výchozí hodnoty dávají „výchozí výpis":
    bez hledání, bez filtrů, řazení podle názvu vzestupně, první stránka.

    - `query`: text hledaný v názvu (bez ohledu na velikost písmen). Prázdný
      nebo jen mezery = bez filtru názvu.
    - `department`: přesná shoda útvaru (hodnota z konfigurovaného výčtu).
    - `classification`: přesná shoda klasifikace (`SMALL`/`MEDIUM`/`LARGE`).
    - `unclassified_only`: jen záznamy bez klasifikace (`classification IS NULL`).
      Vzájemně výlučné s `classification`; když je `True`, `classification` se
      ignoruje.
    - `state`: přesná shoda stavu. `None` = stav nezvolen → výchozí výpis skryje
      vyřazené (R3.9). Konkrétní hodnota (i `DECOMMISSIONED`) = přesně ten stav.
    - `include_decommissioned`: přepínač „Zobrazit i vyřazené" pro výpis **bez**
      zvoleného konkrétního stavu (ui.md sekce 5, tato část úkolu 11.2). Když je
      `True` a `state` je `None`, výchozí skrytí vyřazených se **neuplatní** a
      výpis zahrne všechny stavy včetně `DECOMMISSIONED`. Jakmile je zvolen
      konkrétní `state`, tento přepínač nemá význam — stav se respektuje přesně.
    - `sort_desc`: řazení podle názvu sestupně místo vzestupně.
    - `page` / `page_size`: stránkování (od 1; ořez do platného rozsahu).
    - `trio_member_id`: identita přihlášené osoby pro výpis „Moje aplikace"
      (ui.md sekce 4, R3.10/R4.1/R4.2). Když je vyplněná, výpis se zúží na
      záznamy, kde je tato **identita** členem odpovědné trojice — tedy shoda
      s `owner_user_id`, `deputy_user_id` **nebo** `tech_admin_user_id`.
      Porovnává se výhradně identifikátor osoby, nikdy jméno (R2.6, R4.2).
      Prázdný zástupce (`deputy_user_id IS NULL`) se nesmí shodovat — rovnost
      v SQL nikdy neplatí pro NULL, takže se NULL přirozeně nevybere.
      `None` = běžný výpis registru bez omezení na trojici (výchozí, no-op),
      takže chování úkolu 11.1/11.2 zůstává beze změny.
    """

    query: str | None = None
    department: str | None = None
    classification: Classification | None = None
    unclassified_only: bool = False
    state: LifecycleState | None = None
    include_decommissioned: bool = False
    sort_desc: bool = False
    page: int = 1
    page_size: int = 20
    trio_member_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ListResult:
    """Výsledek výpisu: jedna stránka záznamů plus celkový počet přes filtry.

    `total` je počet záznamů odpovídajících filtrům **napříč všemi stránkami**
    (před `LIMIT`/`OFFSET`), takže route z něj sestaví „Zobrazeno X–Y z N".
    `items` je jen požadovaná stránka.
    """

    items: list[Application] = field(default_factory=list)
    total: int = 0


def _apply_filters(stmt: Select, filters: ListFilters) -> Select:
    """Přidá na dotaz `WHERE` klauzule společné pro výpis i pro počítání.

    Sdílí je stránkovací dotaz i `COUNT`, aby celkový počet vždy odpovídal
    přesně té množině, kterou uživatel vidí (jen bez `LIMIT`/`OFFSET`).
    """
    # Hledání podle názvu bez ohledu na velikost písmen A diakritiku (R3.2).
    # `f_unaccent(lower(...))` na obou stranách LIKE odstraní diakritiku i
    # velikost písmen, takže „pre" najde „pře", „prě", „před" apod. `f_unaccent`
    # je IMMUTABLE obal nad `unaccent` (migrace a1b2c3d4e5f6); dotaz využívá
    # funkcionální index `ix_applications_unaccent_lower_name`. Filtruje databáze,
    # ne aplikace v paměti (R3.6).
    if filters.query and filters.query.strip():
        pattern = f"%{_escape_like(filters.query.strip())}%"
        stmt = stmt.where(
            func.f_unaccent(func.lower(Application.name)).like(
                func.f_unaccent(func.lower(pattern)), escape=_LIKE_ESCAPE
            )
        )

    # Filtry rovnosti (R3.3), kombinovatelné.
    if filters.department:
        stmt = stmt.where(Application.department == filters.department)

    if filters.unclassified_only:
        # Výslovná volba „Neklasifikováno" — záznamy bez platné klasifikace.
        stmt = stmt.where(Application.classification.is_(None))
    elif filters.classification is not None:
        stmt = stmt.where(Application.classification == filters.classification.value)

    # Stav: tři situace v pořadí priority.
    #  1) Zvolený konkrétní stav → přesná shoda (i DECOMMISSIONED), R3.9.
    #  2) Bez stavu, ale „Zobrazit i vyřazené" → žádný filtr stavu, výpis
    #     zahrne všechny stavy včetně vyřazených (ui.md sekce 5).
    #  3) Bez stavu i bez přepínače → výchozí skrytí vyřazených (R3.9).
    if filters.state is not None:
        stmt = stmt.where(Application.lifecycle_state == filters.state.value)
    elif not filters.include_decommissioned:
        stmt = stmt.where(
            Application.lifecycle_state != LifecycleState.DECOMMISSIONED.value
        )

    # „Moje aplikace" — členství v odpovědné trojici podle identity (R3.10,
    # R4.2). Shoda identifikátoru osoby s vlastníkem, zástupcem NEBO technickým
    # správcem. Rovnost v SQL neplatí pro NULL, takže prázdný `deputy_user_id`
    # se nikdy neshodne — zástupce bez hodnoty tedy nespadne do výběru.
    # Zrcadlí `domain.rules._is_trio_member`: porovnávají se identity, ne jména.
    if filters.trio_member_id is not None:
        stmt = stmt.where(
            or_(
                Application.owner_user_id == filters.trio_member_id,
                Application.deputy_user_id == filters.trio_member_id,
                Application.tech_admin_user_id == filters.trio_member_id,
            )
        )

    return stmt


def name_exists(
    session: Session,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> bool:
    """Existuje už záznam se stejným názvem bez ohledu na velikost písmen? (R5.8)

    Zrcadlí funkcionální unikátní index ``uq_applications_lower_name``: porovnává
    ``lower(name)``, takže „Portál" a „portál" jsou pro účely unikátnosti totéž.
    Databázový index je poslední pojistka; tato kontrola existuje proto, aby
    aplikace odmítla duplicitu **s českou hláškou u pole** dřív, než na ni narazí
    ``IntegrityError`` z databáze (design.md 8).

    - **Vytvoření** (úkol 14.2): ``exclude_id=None`` — hledá se jakýkoli záznam
      se shodným názvem.
    - **Editace** (úkol 14.4): ``exclude_id`` = ``id`` upravovaného záznamu — ten
      se z kontroly vynechá, aby uložení beze změny názvu neselhalo na „duplicitě"
      samo se sebou.

    Prázdný nebo jen-mezerový název není duplicita (povinnost názvu řeší validační
    model, ne tato funkce) — vrací ``False``, aby se nehlásila zavádějící kolize.
    """
    trimmed = name.strip()
    if not trimmed:
        return False

    stmt = select(Application.id).where(func.lower(Application.name) == func.lower(trimmed))
    if exclude_id is not None:
        stmt = stmt.where(Application.id != exclude_id)
    return session.execute(stmt.limit(1)).first() is not None


def list_applications(session: Session, filters: ListFilters | None = None) -> ListResult:
    """Vrátí jednu stránku výpisu registru a celkový počet přes filtry.

    Vše dělá databáze; do paměti se načítá jen požadovaná stránka (R3.6).

    Řazení je napevno podle `lower(name)` (vzestupně, volitelně sestupně) —
    nikdy podle názvu sloupce z URL (design.md 6.2). Sekundárně podle `id`,
    aby bylo pořadí stabilní i mezi záznamy se shodným názvem a stránkování
    nepřeskakovalo řádky.

    Stránkování se defenzivně ořeže: `page` nejméně 1, `page_size` nejméně 1.
    Přepočet neplatné stránky mimo rozsah řeší `web/pagination.paginate()`
    v route; zde jde jen o platný `OFFSET`.
    """
    filters = filters or ListFilters()

    page = filters.page if filters.page >= 1 else 1
    page_size = filters.page_size if filters.page_size >= 1 else 1

    # Celkový počet přes stejné filtry, ale bez řazení a stránkování (R3.5).
    count_stmt = _apply_filters(select(func.count()).select_from(Application), filters)
    total = int(session.execute(count_stmt).scalar_one())

    order_column = func.lower(Application.name)
    order_by = order_column.desc() if filters.sort_desc else order_column.asc()

    page_stmt = _apply_filters(select(Application), filters)
    page_stmt = (
        page_stmt.order_by(order_by, Application.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    items = list(session.execute(page_stmt).scalars().all())

    return ListResult(items=items, total=total)


def list_my_applications(
    session: Session,
    user_id: uuid.UUID,
    filters: ListFilters | None = None,
) -> ListResult:
    """Vrátí záznamy, kde je `user_id` členem odpovědné trojice (R3.10, R4.1).

    Obrazovka „Moje aplikace" (ui.md sekce 4). Je to tenká vrstva nad
    `list_applications`: vynutí `trio_member_id = user_id`, aby se výpis omezil
    na záznamy, kde je přihlášená osoba vlastníkem, zástupcem nebo technickým
    správcem — a to porovnáním **identity**, nikdy jména (R4.2). Tím se sdílí
    hledání, řazení, stránkování i celkový počet s výpisem registru (úkol 11.1).

    Členství se rozhoduje shodou identifikátoru osoby; prázdný `deputy_user_id`
    se neshodne (rovnost v SQL neplatí pro NULL), takže NULL zástupce nikdy
    nevytáhne cizí záznam.

    Vyřazené záznamy zůstávají ve výchozím výpisu skryté stejně jako v registru
    (R3.9): „Moje aplikace" jsou pracovní přehled, ne archiv. Vyřazený vlastní
    záznam lze zobrazit stejnými přepínači jako v registru (`state` nebo
    `include_decommissioned`); ui.md sekce 4 pro tuto obrazovku výjimku neuvádí,
    proto držíme shodné výchozí chování jako registr.

    Případný `trio_member_id` ve `filters` se ignoruje — autoritativní je
    `user_id` z argumentu, aby route nemohla omylem zobrazit cizí záznamy.
    """
    base = filters or ListFilters()
    scoped = replace(base, trio_member_id=user_id)
    return list_applications(session, scoped)
