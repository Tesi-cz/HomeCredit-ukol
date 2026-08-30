"""Šablonovací vrstva REGINY (ui.md sekce 3, design.md 4.3).

Zde se skládá Jinja2 a připravuje kontext, který každá stránka potřebuje:
přihlášená osoba, aktivní položka navigace, CSRF token a identita produktu.
Cílem je, aby routy kontext neredeklarovaly — zavolají `page_context(...)`
a doplní jen data své obrazovky.

**Jediný zdroj pravdy pro navigaci.** Sidebar se vykresluje z `nav.NAV_ITEMS`
(viz `web/nav.py`). Kontext sem propašuje jen `active_nav` klíč; `base.html`
porovná klíč proti položkám a zvýrazní shodu. Žádná šablona seznam nepřepisuje.

**Rozhraní se neodpojí od vynucení.** Viditelnost položek Uživatelé/Auditní
logy řídí `nav.visible_nav_items(role)`, tedy roli aktéra — skrytí je jen
pohodlnost, cesty zůstávají chráněné guardy na backendu (R2.5).

**Globální funkce šablon.** `get_csrf_token` je v prostředí dostupná jako
funkce, aby formuláře (např. odhlášení) mohly vložit skryté pole i mimo
předpřipravený kontext. `initials` počítá iniciály z jména pro avatar.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates

from regina.auth.csrf import get_csrf_token
from regina.auth.deps import CurrentUser
from regina.domain import labels
from regina.domain.enums import (
    AuditAction,
    Classification,
    ClassificationSource,
    LifecycleState,
    Role,
)
from regina.web.flash import flash_from_request
from regina.web.nav import PRIMARY_ACTION, NavItem, visible_nav_items

# Šablony leží vedle tohoto modulu v `templates/`. Cesta se počítá z umístění
# souboru, aby fungovala nezávisle na pracovním adresáři (uvicorn i testy).
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Přeložené CSS pro cache-busting odkazu v base.html (viz `asset_version`).
_APP_CSS_PATH = Path(__file__).resolve().parent / "static" / "css" / "app.css"


@lru_cache(maxsize=1)
def asset_version() -> str:
    """Krátký otisk obsahu `app.css` pro cache-busting (`?v=…` u odkazu na CSS).

    Prohlížeč jinak drží starou verzi CSS ve své cache i po redeploy (soubor má
    pořád stejnou cestu `/static/css/app.css`), takže se změny rozvržení
    neprojeví, dokud uživatel ručně nepřenačte cache. Připojením otisku obsahu
    k URL se s každou změnou CSS změní i odkaz, takže si prohlížeč vynuceně
    stáhne aktuální soubor. Otisk se počítá jednou (obsah se za běhu nemění);
    když soubor chybí (např. test bez build stupně), vrací se `dev`, aby se
    šablona nerozbila.
    """
    try:
        digest = hashlib.sha256(_APP_CSS_PATH.read_bytes()).hexdigest()
    except OSError:
        return "dev"
    return digest[:12]


def initials(name: str | None) -> str:
    """Vrátí iniciály z jména pro avatar přihlášené osoby (ui.md sekce 3).

    Vezme první písmeno prvního a posledního slova. U jednoslovného jména jen
    jeho první písmeno; u prázdného vstupu zástupné „?", aby avatar nikdy
    nezůstal prázdný.
    """
    if not name:
        return "?"
    parts = [part for part in name.split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# Zástupný znak pro chybějící datum. Pomlčka místo prázdna, aby buňka tabulky
# ani řádek detailu nezůstal opticky prázdný a bylo zřejmé, že hodnota chybí.
_MISSING_DATE = "—"


def datum(value: date | datetime | None) -> str:
    """Naformátuje datum do českého tvaru DD.MM.YYYY (R13.3).

    Jediný vstupní bod pro formátování data v rozhraní — šablony nikdy
    neformátují datum ručně, volají tento filtr. Přijímá `date` i `datetime`
    (u datetime se čas zahodí). Pro `None` vrací pomlčku, aby se prázdná
    hodnota nezobrazila jako mezera.
    """
    if value is None:
        return _MISSING_DATE
    return value.strftime("%d.%m.%Y")


def datum_cas(value: datetime | None) -> str:
    """Naformátuje datum a čas do tvaru DD.MM.YYYY HH:MM (R13.3, ui.md sekce 9).

    Varianta pro časová razítka auditního logu, kde je vedle data potřeba i čas.
    Jediný vstupní bod stejně jako `datum` — žádné ruční formátování v šablonách.
    Pro `None` vrací pomlčku.
    """
    if value is None:
        return _MISSING_DATE
    return value.strftime("%d.%m.%Y %H:%M")


# Barevné varianty badge komponent (ui.md sekce 4 a 5, mocky). Klíčem je
# strojový kód výčtu, hodnotou je *jméno varianty* — ne přímo Tailwind třídy.
# Konkrétní třídy pro každou variantu drží šablona `components/badges.html`,
# takže Tailwind je při buildu vidí ve statickém HTML a nevyřadí je. Zde je jen
# rozhodnutí „který stav má kterou barvu", ať je na jednom místě a testovatelné.
#
# Popisek badge se *nikdy* nebere odsud — vždy z `labels.py` (R13.11). Tyto
# mapy řídí jen vzhled.

#: Varianta badge stavu podle fáze životního cyklu. Produkce je „živá" (teal),
#: vyřazená je ztlumená, ostatní neutrální/průběžné.
_LIFECYCLE_STATE_VARIANTS: dict[LifecycleState, str] = {
    LifecycleState.DRAFT: "neutral",
    LifecycleState.IN_DEVELOPMENT: "progress",
    LifecycleState.TESTING: "progress",
    LifecycleState.IN_PRODUCTION: "live",
    LifecycleState.DECOMMISSIONED: "muted",
}

#: Varianta badge klasifikace. Úrovně jsou neutrální (ui.md „neutrální"),
#: odstíněné podle velikosti; absence klasifikace má vlastní výraznou variantu.
_CLASSIFICATION_VARIANTS: dict[Classification, str] = {
    Classification.SMALL: "small",
    Classification.MEDIUM: "medium",
    Classification.LARGE: "large",
}

#: Varianta badge role. Správce je zvýrazněný, uživatel neutrální.
_ROLE_VARIANTS: dict[Role, str] = {
    Role.USER: "neutral",
    Role.ADMIN: "admin",
}

#: Varianta badge klasifikace pro záznam bez klasifikace (R3.8). Odlišná od
#: úrovní, aby „Neklasifikováno" bylo na první pohled jiné než MALÁ/STŘEDNÍ/VELKÁ.
NO_CLASSIFICATION_VARIANT = "none"


def lifecycle_state_variant(value: LifecycleState) -> str:
    """Vrátí jméno barevné varianty pro badge stavu (ui.md sekce 5)."""
    return _LIFECYCLE_STATE_VARIANTS[value]


def classification_variant(value: Classification | None) -> str:
    """Vrátí jméno varianty pro badge klasifikace, včetně stavu bez klasifikace.

    Pro `None` vrací `NO_CLASSIFICATION_VARIANT` (R3.8), jinak variantu úrovně.
    Zrcadlí `labels.classification_label`, aby vzhled i popisek řešily `None`
    stejně a na jednom volání.
    """
    if value is None:
        return NO_CLASSIFICATION_VARIANT
    return _CLASSIFICATION_VARIANTS[value]


def role_variant(value: Role) -> str:
    """Vrátí jméno barevné varianty pro badge role (ui.md sekce 8)."""
    return _ROLE_VARIANTS[value]


def lifecycle_enum(value: str | LifecycleState | None) -> LifecycleState | None:
    """Přeloží uložený strojový kód stavu na člen výčtu pro badge komponentu.

    Model drží `lifecycle_state` jako `text` (database.md 6.4), ale badge
    komponenta i mapy variant pracují se členem `LifecycleState`. Tento filtr
    je most: šablona zavolá `zaznam.lifecycle_state | lifecycle_enum` a předá
    výsledek `state_badge(...)`. Člen výčtu projde beze změny, `None` zůstane
    `None`.
    """
    if value is None or isinstance(value, LifecycleState):
        return value
    return LifecycleState(value)


def classification_enum(value: str | Classification | None) -> Classification | None:
    """Přeloží uložený strojový kód klasifikace na člen výčtu, nebo `None`.

    Klasifikace je nullable (`None` = neklasifikováno, R3.8); v tom případě se
    vrací `None`, které badge i popisek zpracují jako „Neklasifikováno". Člen
    výčtu projde beze změny.
    """
    if value is None or isinstance(value, Classification):
        return value
    return Classification(value)


def classification_source_enum(
    value: str | ClassificationSource | None,
) -> ClassificationSource | None:
    """Přeloží uložený strojový kód zdroje klasifikace na člen výčtu, nebo `None`.

    Řádek `classification_log.source` je `text` (database.md 6.4), ale popisek
    se bere z `labels.label`, který přijímá člen výčtu `ClassificationSource`.
    Tento filtr je most: detail zavolá `radek.source | classification_source_enum`
    a výsledek předá do `label(...)`, aby se zobrazil český popisek (Člověk /
    Přepis správce), nikdy strojový kód (R13.11). Člen výčtu projde beze změny,
    `None` zůstane `None`.
    """
    if value is None or isinstance(value, ClassificationSource):
        return value
    return ClassificationSource(value)


def audit_action_enum(value: str | AuditAction) -> AuditAction:
    """Přeloží uložený strojový kód akce na člen `AuditAction` pro popisek.

    `audit_log.action` je `text` (database.md 6.4), ale popisek se bere z
    `labels.label`, který přijímá člen výčtu `AuditAction`. Tento filtr je most:
    šablona auditního výpisu zavolá `zaznam.action | audit_action_enum` a
    výsledek předá do `label(...)`, aby se zobrazil český popisek, nikdy strojový
    kód (R13.11, ui.md sekce 9). Člen výčtu projde beze změny. Akce je vždy
    vyplněná (`nullable=False`), proto se `None` neřeší.
    """
    if isinstance(value, AuditAction):
        return value
    return AuditAction(value)


def page_url(request: Request, page: int) -> str:
    """Sestaví URL aktuální cesty s přepsaným parametrem `page` (ui.md sekce 5).

    Stránkování musí zachovat aktivní vyhledávání a filtry — odkaz na jinou
    stránku proto vezme stávající query string požadavku a přepíše v něm jen
    `page`. Komponenta `pagination.html` tak nemusí znát názvy filtrů dané
    obrazovky. Bez tohoto by přeskok na stránku 2 zahodil vybrané filtry.
    """
    params = dict(request.query_params)
    params["page"] = str(page)
    return f"{request.url.path}?{urlencode(params)}"


def build_templates() -> Jinja2Templates:
    """Sestaví konfiguraci Jinja2 s globálními funkcemi šablon.

    `autoescape` je u Jinja2Templates zapnutý implicitně pro .html, takže
    uživatelský vstup se escapuje. Globály jsou funkce, které šablona volá
    přímo (`get_csrf_token(request)`, `initials(jmeno)`).
    """
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    templates.env.globals["get_csrf_token"] = get_csrf_token
    templates.env.globals["initials"] = initials

    # Formátování data do českého tvaru DD.MM.YYYY (R13.3). Jediný vstupní bod —
    # žádná šablona datum neformátuje ručně. Registrováno jako filtr
    # (`{{ zaznam.updated_at | datum }}`) i jako globál pro případné volání.
    # `datum_cas` přidává čas pro razítka auditního logu (ui.md sekce 9).
    templates.env.filters["datum"] = datum
    templates.env.filters["datum_cas"] = datum_cas
    templates.env.globals["datum"] = datum
    templates.env.globals["datum_cas"] = datum_cas

    # Popisky výčtů do rozhraní výhradně přes labels.py (R13.11). Badge
    # komponenty volají `label(...)` a `classification_label(...)`, nikdy
    # nevykreslují strojový kód.
    templates.env.globals["label"] = labels.label
    templates.env.globals["classification_label"] = labels.classification_label
    templates.env.globals["NO_CLASSIFICATION_LABEL"] = labels.NO_CLASSIFICATION_LABEL

    # Barevné varianty badge komponent (jen vzhled, ne text).
    templates.env.globals["lifecycle_state_variant"] = lifecycle_state_variant
    templates.env.globals["classification_variant"] = classification_variant
    templates.env.globals["role_variant"] = role_variant

    # Odkaz stránkování zachovávající filtry (komponenta pagination.html).
    templates.env.globals["page_url"] = page_url

    # Převod uloženého strojového kódu na člen výčtu pro badge komponenty. Model
    # drží stav a klasifikaci jako `text` (database.md 6.4), badge ale pracuje
    # se členem výčtu — filtr je most (`zaznam.lifecycle_state | lifecycle_enum`).
    templates.env.filters["lifecycle_enum"] = lifecycle_enum
    templates.env.filters["classification_enum"] = classification_enum
    # Zdroj klasifikace (Člověk / Přepis správce) na detailu (R4.4, R4.6).
    templates.env.filters["classification_source_enum"] = classification_source_enum
    # Typ auditní akce na strojovém kódu → člen výčtu pro popisek (ui.md sekce 9).
    templates.env.filters["audit_action_enum"] = audit_action_enum

    return templates


def page_context(
    request: Request,
    *,
    active_nav: str | None = None,
    section_title: str = "",
    user: CurrentUser | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Sestaví kontext pro vykreslení stránky nad `base.html`.

    Routy volají tuto funkci místo ručního skládání dictu, aby se navigace,
    identita produktu a CSRF držely na jednom místě. `active_nav` je klíč
    zvýrazněné položky (viz `nav.NavItem.key`), `section_title` se vypisuje
    v horní liště, `user` je přihlášená osoba nebo `None`. Další data obrazovky
    se předají přes `**extra`.

    `nav_items` se filtruje podle role aktéra (`visible_nav_items`); pro
    nepřihlášený kontext (`user is None`) se sidebar nevykresluje, takže se
    vrací prázdná n-tice.
    """
    settings = request.app.state.settings
    nav_items: tuple[NavItem, ...] = visible_nav_items(user.role) if user is not None else ()

    context: dict[str, Any] = {
        "request": request,
        "app_name": settings.app_name,
        "app_subtitle": settings.app_subtitle,
        # Otisk CSS pro cache-busting odkazu v base.html (viz asset_version).
        "asset_version": asset_version(),
        "user": user,
        "active_nav": active_nav,
        "section_title": section_title,
        "nav_items": nav_items,
        "primary_action": PRIMARY_ACTION,
        "csrf_token": get_csrf_token(request),
        # Hlášení o výsledku akce z query parametrů (Post/Redirect/Get). `None`,
        # když se na obrazovku nepřišlo s flash parametrem (web/flash.py, R13.8).
        "flash": flash_from_request(request),
    }
    context.update(extra)
    return context
