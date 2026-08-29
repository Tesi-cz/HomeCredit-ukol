"""Routy exportu CSV `/export/registr` a `/export/audit` (úkol 18.1, R10).

Svislý řez od parametrů URL po stažitelný soubor. Routa **nefiltruje ani
neskládá CSV** — sesbírá tytéž parametry jako obrazovkový výpis, přeloží je na
filtry a předá je `services/export.py`, který v databázi načte filtrovanou
množinu a vrátí hotové bajty. Route je jen zabalí do odpovědi ke stažení.

**Kdo smí exportovat — jen Admin (R10.1, R10.2, R10.4).** Obě routy chrání
guard `require_export` (`auth/deps.py`), který vynutí `rules.can_export` **na
backendu**: přihlášený uživatel role User dostane 403 + audit `ACCESS_DENIED`
i při **přímém** GET, i když mu rozhraní tlačítko „Exportovat CSV" nikdy
neukázalo (R10.4, R2.2). Skrytí tlačítka je pohodlnost, vynucení leží zde.

**Filtrovaná množina (R10.3).** Parametry z URL se mapují na `ListFilters`,
respektive `AuditFilters` — **stejným** způsobem jako obrazovkové routy
(`registry.py`, `audit.py`), takže export odpovídá přesně tomu, co uživatel
vidí na obrazovce. Tlačítko „Exportovat CSV" proto vede na tuto cestu se
**zkopírovaným query stringem** aktuálního výpisu, aby se filtry přenesly.

**Odpověď ke stažení.** Vrací `Response` s tělem `text/csv; charset=utf-8` a
hlavičkou `Content-Disposition: attachment; filename=…`. CSV bajty už nesou
UTF-8 BOM (rozhodnutí `services/export.py`), aby Excel zobrazil českou
diakritiku správně. Filename je český název s příponou `.csv`.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from typing import Annotated

from fastapi import Depends

from regina.auth.deps import CurrentUser, SessionDep, require_export
from regina.domain.enums import AuditAction, Classification, LifecycleState
from regina.repositories.applications import ListFilters
from regina.repositories.audit import AuditFilters
from regina.services.export import export_audit_csv, export_registry_csv

router = APIRouter(tags=["export"])

# Guard aktéra vyhrazený roli Admin (R10.4). Vrací přihlášeného aktéra.
ExportActorDep = Annotated[CurrentUser, Depends(require_export)]

# MIME typ CSV s explicitním UTF-8 (R10.5). Bajty navíc nesou BOM (viz export
# service), takže Excel poznal kódování i bez spoléhání na charset.
_CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


def _parse_enum(value: str | None, enum_type):
    """Přeloží strojový kód z URL na člen výčtu, nebo `None`.

    Neznámá či prázdná hodnota = „nezvoleno" — ručně upravený odkaz
    (`?stav=NESMYSL`) export neshodí, jen se filtr neuplatní. Zrcadlí chování
    obrazovkových rout (`registry.py`, `audit.py`), aby export honoroval filtry
    přesně jako výpis.
    """
    if not value:
        return None
    try:
        return enum_type(value)
    except ValueError:
        return None


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    """Přeloží identifikátor z URL na `UUID`, nebo `None` při nesmyslu."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    """Přeloží datum z URL (ISO `YYYY-MM-DD`) na `date`, nebo `None`."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _download(filename: str, body: bytes) -> Response:
    """Zabalí CSV bajty do odpovědi ke stažení (`Content-Disposition`).

    Tělo je `text/csv; charset=utf-8`; `filename` český název s příponou `.csv`.
    Bajty už nesou UTF-8 BOM (rozhodnutí export service).
    """
    return Response(
        content=body,
        media_type=_CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/registr", include_in_schema=False, response_model=None)
def export_registry(
    request: Request,
    user: ExportActorDep,
    session: SessionDep,
    q: str | None = Query(default=None),
    utvar: str | None = Query(default=None),
    klasifikace: str | None = Query(default=None),
    stav: str | None = Query(default=None),
    vse: bool = Query(default=False),
) -> Response:
    """Stáhne registr aplikací jako CSV, honoruje filtry výpisu (R10.1, R10.3).

    Vyhrazeno roli Admin (`require_export`); role User skončí 403 + audit
    `ACCESS_DENIED` (R10.4, R2.2). Parametry z URL se mapují na `ListFilters`
    **shodně** s routou `/registr` (úkol 11.2), takže export odpovídá přesně
    tomu, co uživatel vidí — jen bez stránkování (R10.3). Stránka se úmyslně
    **nepředává**: exportuje se celá filtrovaná množina.
    """
    settings = request.app.state.settings

    department = utvar if utvar in settings.departments else None
    unclassified_only = klasifikace == "NONE"
    classification = None if unclassified_only else _parse_enum(klasifikace, Classification)
    state = _parse_enum(stav, LifecycleState)

    filters = ListFilters(
        query=q,
        department=department,
        classification=classification,
        unclassified_only=unclassified_only,
        state=state,
        include_decommissioned=vse,
    )

    filename, body = export_registry_csv(session, filters)
    return _download(filename, body)


@router.get("/export/audit", include_in_schema=False, response_model=None)
def export_audit(
    request: Request,
    user: ExportActorDep,
    session: SessionDep,
    akce: str | None = Query(default=None),
    akter: str | None = Query(default=None),
    od: str | None = Query(default=None),
    do: str | None = Query(default=None),
) -> Response:
    """Stáhne auditní log jako CSV, honoruje filtry výpisu (R10.2, R10.3).

    Vyhrazeno roli Admin (`require_export`); role User skončí 403 + audit
    `ACCESS_DENIED` (R10.4, R2.2). Parametry z URL se mapují na `AuditFilters`
    **shodně** s routou `/audit` (úkol 17.1), takže export odpovídá přesně
    výpisu — jen bez stránkování (R10.3).
    """
    filters = AuditFilters(
        action=_parse_enum(akce, AuditAction),
        actor_user_id=_parse_uuid(akter),
        date_from=_parse_date(od),
        date_to=_parse_date(do),
    )

    filename, body = export_audit_csv(session, filters)
    return _download(filename, body)
