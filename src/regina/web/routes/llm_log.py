"""Routa výpisu logu volání modelu `/volani-ai` (classification-advisor R6.3).

Read-only přehled technických záznamů volání modelu od nejnovějšího:
implementace, model, operace, tokeny, latence, stav, čas. **Bez obsahu** — ten
se neukládá (R6.2), takže výpis ani nemá co citlivého zobrazit.

**Kdo obrazovku vidí — jen Admin (R6.3).** Guard `require_read_audit` vynutí
`rules.can_read_audit` na backendu, stejně jako u auditního logu: role User
dostane 403 + audit `ACCESS_DENIED`, i když jí sidebar položku „Volání AI"
nikdy neukázal (nav ji roli User skrývá).

Vzor zrcadlí `routes/audit.py`: sdílený `_context` pro stránku i fragment,
stránkování přes `paginate`, živé překreslování přes `/volani-ai/fragment`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from regina.auth.deps import CurrentUser, SessionDep, require_read_audit
from regina.repositories.llm_call_log import list_calls
from regina.web.pagination import paginate
from regina.web.templating import page_context

router = APIRouter(tags=["llm-log"])

# Velikost stránky výpisu, shodně s auditem (ui.md sekce 9).
_PAGE_SIZE = 20

# Guard vyhrazený roli Admin (R6.3) — tentýž jako čtení auditu.
LogReaderDep = Annotated[CurrentUser, Depends(require_read_audit)]


def _context(request: Request, user: CurrentUser, session: SessionDep, *, page: int) -> dict:
    """Sestaví kontext výpisu pro stránku i fragment (shodná data).

    Načte jednu stránku z repozitáře a z celkového počtu sestaví stránkování.
    Filtrování ani řazení podle URL se nedělá — výpis je prostý přehled.
    """
    result = list_calls(session, page=page, page_size=_PAGE_SIZE)
    pagination = paginate(total=result.total, page=page, page_size=_PAGE_SIZE)
    return page_context(
        request,
        active_nav="volani-ai",
        section_title="Volání AI",
        user=user,
        entries=result.items,
        pagination=pagination,
    )


@router.get("/volani-ai", include_in_schema=False)
def llm_log_list(
    request: Request,
    user: LogReaderDep,
    session: SessionDep,
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vykreslí výpis volání modelu (R6.3). Vyhrazeno roli Admin."""
    context = _context(request, user, session, page=page)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "llm_log/list.html", context)


@router.get("/volani-ai/fragment", include_in_schema=False)
def llm_log_fragment(
    request: Request,
    user: LogReaderDep,
    session: SessionDep,
    page: int = Query(default=1),
) -> HTMLResponse:
    """Vrátí jen výsledky (tabulka + stránkování) pro živé překreslování.

    Stejný partial i kontext jako celá stránka, takže se nikdy nerozejdou.
    Vyhrazeno roli Admin stejně jako `/volani-ai` — fragment autorizaci neobejde.
    """
    context = _context(request, user, session, page=page)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "llm_log/_results.html", context)
