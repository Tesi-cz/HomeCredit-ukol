"""Routy AI funkcí formuláře (classification-advisor R2, R3, R4).

Dva POST endpointy volané z formuláře přes fetch (progresivní vylepšení, vzor
`live-search.js`): oba vrací **HTML fragment**, kterým JS nahradí příslušný
kontejner. Bez JS zůstává formulář plně funkční — klasifikaci i popis lze zadat
ručně (poradce je nadstavba, ne podmínka).

- ``POST /registr/poradce`` — z odpovědí dotazníku sestaví doporučení (přes
  ``services/advisor``) a vrátí AI panel s navrženou úrovní, zdůvodněním a
  rozpadem skóre (R3.3). Panel nabídne skryté pole ``classification`` k
  předvyplnění a odkaz na ``suggestion_id`` pro zápis se zdrojem AI.
- ``POST /registr/uprava-popisu`` — přepíše zadaný popis (přes
  ``services/description_rewrite``) a vrátí návrh k převzetí, nebo nezávaznou
  chybu (R4.5).

**Autorizace.** Obě routy vyžadují přihlášení (``CurrentUserDep``) a CSRF token
(``CsrfProtect``). Samotný **zápis** klasifikace se tu neděje — proběhne až
uložením formuláře přes ``registry`` routy s guardem ``require_can_edit`` /
``require_can_set_classification`` (R3.10). Poradce jen připraví návrh.

**Anonymizace.** Jména z adresáře se předají službám jako ``known_names``, aby
se maskovala v poznámce i v popisu před odesláním modelu (R5.3).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from regina.auth.csrf import CsrfProtect
from regina.auth.deps import CurrentUserDep, SessionDep
from regina.domain import questionnaire
from regina.domain.enums import Classification
from regina.repositories import users as users_repo
from regina.services import advisor, description_rewrite
from regina.web.deps import LLMClientDep

router = APIRouter(tags=["advisor"])


def _known_names(session: SessionDep) -> list[str]:
    """Jména z adresáře pro anonymizaci (R5.3). Aktivní osoby stačí."""
    return [p.display_name for p in users_repo.list_active(session) if p.display_name]


async def _read_form(request: Request) -> dict[str, str]:
    """Přečte formulářová pole jako mapu (bez CSRF pole)."""
    data = await request.form()
    return {k: v for k, v in data.items() if k != "csrf_token" and isinstance(v, str)}


@router.post("/registr/poradce", include_in_schema=False, dependencies=[CsrfProtect])
async def advisor_suggest(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    client: LLMClientDep,
) -> HTMLResponse:
    """Vrátí AI panel s doporučením klasifikace z odpovědí dotazníku (R3).

    Odpovědi přijme z formuláře (pole pojmenovaná dle dimenzí ``dim_<DIMENZE>``),
    volitelnou poznámku z ``poradce_poznamka``. Neúplné odpovědi → panel s
    výzvou doplnit (R2.4), request nespadne. Jinak zavolá ``advisor`` (fallback
    řeší služba, R3.4) a vrátí panel s navrženou úrovní, zdůvodněním a skóre.
    """
    form = await _read_form(request)
    answers = {
        q.dimension: form.get(f"dim_{q.dimension}", "").strip()
        for q in questionnaire.QUESTIONS
    }
    note = form.get("poradce_poznamka", "").strip() or None

    templates = request.app.state.templates

    missing = questionnaire.missing_dimensions(answers)
    if missing:
        # Neúplný dotazník — panel jen vyzve k doplnění, model se nevolá.
        return templates.TemplateResponse(
            request,
            "registry/_advisor_panel.html",
            {"request": request, "incomplete": True},
        )

    suggestion = advisor.request_suggestion(
        session,
        client,
        answers=answers,
        note=note,
        known_names=_known_names(session),
        requested_by_user_id=user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    # Rozpad skóre po dimenzích s českými popisky dimenzí (title otázky).
    breakdown_rows = [
        {
            "title": q.title,
            "score": suggestion.score_breakdown[q.dimension],
        }
        for q in questionnaire.QUESTIONS
    ]

    return templates.TemplateResponse(
        request,
        "registry/_advisor_panel.html",
        {
            "request": request,
            "incomplete": False,
            "suggestion": suggestion,
            "breakdown_rows": breakdown_rows,
            "score_max": questionnaire.SCORE_MAX,
        },
    )


@router.post("/registr/uprava-popisu", include_in_schema=False, dependencies=[CsrfProtect])
async def advisor_rewrite(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    client: LLMClientDep,
) -> HTMLResponse:
    """Vrátí návrh přepsaného popisu, nebo nezávaznou chybu (R4).

    Popis přijme z pole ``popis``. Prázdný popis i chyba modelu vrací fragment
    s českou hláškou; původní popis se nemění (R4.4, R4.5). Návrh se nikam
    neukládá — převzetí řeší JS ve formuláři, uložení až odeslání formuláře.
    """
    form = await _read_form(request)
    description = form.get("popis", "")

    result = description_rewrite.rewrite_description(
        session,
        client,
        description=description,
        known_names=_known_names(session),
        requested_by_user_id=user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
    )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "registry/_rewrite_result.html",
        {"request": request, "result": result},
    )
