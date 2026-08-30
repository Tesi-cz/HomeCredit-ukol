"""Retenční rutina (design.md 9, R9).

Osobní údaje se v registru nedrží donekonečna. Retence je automatická úloha,
která pro každou kategorii spočítá hranici a smaže řádky za ní. Žádný plánovač
navíc, žádný ruční krok (R9.3): úloha se spustí při startu aplikace a pak běží
v konfigurovatelném intervalu (`RETENTION_INTERVAL_HOURS`).

**Dvě kategorie** (design.md 9, R9.1):

| Kategorie | Hranice od | Proměnná |
|---|---|---|
| Auditní záznamy | `occurred_at` | `RETENTION_AUDIT_LOG_DAYS` |
| Vyřazené záznamy | `decommissioned_at` | `RETENTION_DECOMMISSIONED_APP_DAYS` |

Hranice se vždy počítá z `decommissioned_at`, nikdy z času poslední úpravy
(R9.4) — editace vyřazeného záznamu jeho retenci neprodlouží.

**Kaskády a přežití auditu** (R9.7). Smazání vyřazené aplikace odstraní
kaskádou její historii klasifikace (`classification_log.application_id` má
`ON DELETE CASCADE`), ale její auditní záznamy **zůstávají** — `audit_log.entity_id`
není cizí klíč, takže na aplikaci nedrží žádnou vazbu. Odpovědná trojice míří
na `users` s `ON DELETE RESTRICT`, ale tady mažeme samotnou aplikaci (dítě
v `classification_log`), ne osobu, takže žádné omezení neporušíme.

**Mazání auditu.** Auditní tabulka je přírůstková — aplikace nad ní nikdy
nevydá `DELETE` (R8.5). Jediná povolená výjimka je právě tato rutina, a i ta
musí své mazání obalit do `audit_guard.audit_retention_context(session)`.
Mimo tento kontext pojistka `DELETE` nad `audit_log` odmítne.

**Vědomé omezení.** Při více instancích aplikace by úloha běžela vícekrát.
Mazání je idempotentní, takže to nezpůsobí chybu, jen zbytečnou práci. Skutečné
řešení je zámek v databázi nebo externí plánovač; pro jednu instanci je to
nadbytečné a v README je to uvedené jako dluh.

Každý běh se loguje po kategoriích (kategorie, hranice, počet smazaných) přímo
v `run_retention_once`, takže se běh zaznamená vždy, bez ohledu na volajícího
(R9.5). Log nese jen počty a časové hranice, nikdy osobní údaje (R12.10).
`run_retention_once` navíc vrací strukturované počty (`RetentionResult`), aby
z nich mohl číst i plánovač a případné testy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from regina.config import Settings
from regina.db import audit_guard
from regina.db import session as db_session
from regina.db.models.applications import Application
from regina.db.models.audit_log import AuditLog
from regina.db.models.classification_suggestion import ClassificationSuggestion
from regina.db.models.llm_call_log import LLMCallLog
from regina.logging import get_logger

logger = get_logger("regina.retention")


@dataclass(frozen=True)
class RetentionResult:
    """Výsledek jednoho běhu retence.

    Nese počty smazaných řádků po kategoriích a hranice, které se použily.
    Plánovač i případné testy (úkol 19.3) čtou z tohoto objektu; samotné
    logování běhu (R9.5) probíhá v `run_retention_once` po kategoriích.
    """

    audit_deleted: int
    apps_deleted: int
    audit_cutoff: datetime
    apps_cutoff: datetime
    # Kategorie poradce (classification-advisor R7).
    llm_calls_deleted: int = 0
    suggestions_deleted: int = 0
    llm_calls_cutoff: datetime | None = None
    suggestions_cutoff: datetime | None = None


def run_retention_once(settings: Settings, *, now: datetime | None = None) -> RetentionResult:
    """Provede jeden běh retence ve vlastní transakci a vrátí počty smazaných.

    Otevře si vlastní `session_scope` (jedna transakce na běh, design.md 6.3),
    protože běží mimo požadavek — nemá závislostí spravovanou session. Commit
    proběhne při úspěchu, rollback při výjimce; obě kategorie se tak smažou
    atomicky, nebo vůbec.

    Hranice se počítají z `now` (výchozí aktuální čas v UTC) a nakonfigurovaných
    počtů dní. `now` je parametr kvůli testovatelnosti.

    Po smazání zaloguje jeden strukturovaný záznam na kategorii (kategorie,
    hranice, počet smazaných) — i při nule (R9.5). Vrací `RetentionResult`
    s počty a hranicemi.
    """
    reference = now or datetime.now(UTC)
    audit_cutoff = reference - timedelta(days=settings.retention_audit_log_days)
    apps_cutoff = reference - timedelta(days=settings.retention_decommissioned_app_days)
    llm_calls_cutoff = reference - timedelta(days=settings.retention_llm_call_log_days)
    suggestions_cutoff = reference - timedelta(days=settings.retention_suggestion_days)

    with db_session.session_scope() as session:
        audit_deleted = _delete_expired_audit(session, audit_cutoff)
        apps_deleted = _delete_expired_decommissioned_apps(session, apps_cutoff)
        # Kategorie poradce (classification-advisor R7.2). Mazání nese
        # `ON DELETE SET NULL` na vazbách, takže úklid technických dat nikdy
        # neutrhne historii klasifikace ani nespadne na cizím klíči (R7.3).
        llm_calls_deleted = _delete_expired_llm_calls(session, llm_calls_cutoff)
        suggestions_deleted = _delete_expired_suggestions(session, suggestions_cutoff)

    _log_run(
        category="audit_log",
        category_label="Auditní záznamy",
        cutoff=audit_cutoff,
        deleted=audit_deleted,
    )
    _log_run(
        category="decommissioned_applications",
        category_label="Vyřazené záznamy",
        cutoff=apps_cutoff,
        deleted=apps_deleted,
    )
    _log_run(
        category="llm_call_log",
        category_label="Logy volání modelu",
        cutoff=llm_calls_cutoff,
        deleted=llm_calls_deleted,
    )
    _log_run(
        category="classification_suggestions",
        category_label="Doporučení poradce",
        cutoff=suggestions_cutoff,
        deleted=suggestions_deleted,
    )

    return RetentionResult(
        audit_deleted=audit_deleted,
        apps_deleted=apps_deleted,
        audit_cutoff=audit_cutoff,
        apps_cutoff=apps_cutoff,
        llm_calls_deleted=llm_calls_deleted,
        suggestions_deleted=suggestions_deleted,
        llm_calls_cutoff=llm_calls_cutoff,
        suggestions_cutoff=suggestions_cutoff,
    )


def _log_run(*, category: str, category_label: str, cutoff: datetime, deleted: int) -> None:
    """Zaloguje výsledek retence pro jednu kategorii (R9.5).

    Strukturovaný záznam nese jen tři údaje: strojový klíč kategorie
    (`category`), použitou hranici v ISO formátu (`cutoff`) a počet smazaných
    řádků (`deleted`). Loguje se i při nule — je to důkaz, že retence proběhla.

    **Bez osobních údajů (R12.10).** Nikdy se neloguje, které konkrétní
    záznamy nebo osoby byly smazány — žádná jména, e-maily, obsah řádků ani
    identifikátory dotčených řádků. Jen počty a časová hranice.
    """
    logger.info(
        "Retence dokončila kategorii %s: hranice %s, smazáno %d",
        category_label,
        cutoff.isoformat(),
        deleted,
        extra={
            "event": "retention.category_completed",
            "category": category,
            "category_label": category_label,
            "cutoff": cutoff.isoformat(),
            "deleted": deleted,
        },
    )


def _delete_expired_audit(session: Session, cutoff: datetime) -> int:
    """Smaže auditní řádky s `occurred_at < cutoff`. Vrátí počet smazaných.

    `DELETE` nad `audit_log` je povolený **jen** uvnitř retenčního kontextu —
    mimo něj ho pojistka nemazatelnosti odmítne (R8.5). Proto je celé mazání
    obalené v `audit_retention_context`.
    """
    statement = delete(AuditLog).where(AuditLog.occurred_at < cutoff)
    with audit_guard.audit_retention_context(session):
        result = session.execute(statement)
    return result.rowcount or 0


def _delete_expired_decommissioned_apps(session: Session, cutoff: datetime) -> int:
    """Smaže vyřazené aplikace s `decommissioned_at < cutoff`. Vrátí počet.

    Hranice se počítá z `decommissioned_at`, nikdy z času poslední úpravy
    (R9.4). Smazání aplikace odstraní kaskádou její `classification_log`
    (`ON DELETE CASCADE`); její auditní záznamy zůstávají, protože
    `audit_log.entity_id` není cizí klíč (R9.7).
    """
    statement = delete(Application).where(
        Application.lifecycle_state == "DECOMMISSIONED",
        Application.decommissioned_at < cutoff,
    )
    result = session.execute(statement)
    return result.rowcount or 0


def _delete_expired_llm_calls(session: Session, cutoff: datetime) -> int:
    """Smaže logy volání modelu s `occurred_at < cutoff` (classification-advisor R7.2).

    Log neobsahuje osobní údaje (R6.2), přesto se maže — držíme jen to, co je
    potřeba pro přehled o nákladech. Vazba `classification_suggestions.llm_call_id`
    je `ON DELETE SET NULL`, takže smazání logu jen vynuluje odkaz z doporučení,
    nic neutrhne (R7.3).
    """
    statement = delete(LLMCallLog).where(LLMCallLog.occurred_at < cutoff)
    result = session.execute(statement)
    return result.rowcount or 0


def _delete_expired_suggestions(session: Session, cutoff: datetime) -> int:
    """Smaže doporučení poradce s `created_at < cutoff` (classification-advisor R7.2).

    Vazba `classification_log.suggestion_id` je `ON DELETE SET NULL`, takže
    smazání doporučení jen vynuluje odkaz z historie klasifikace — nemazatelná
    historie zůstává (R7.3).
    """
    statement = delete(ClassificationSuggestion).where(
        ClassificationSuggestion.created_at < cutoff
    )
    result = session.execute(statement)
    return result.rowcount or 0


async def run_retention_loop(settings: Settings) -> None:
    """Spustí retenci hned při startu a pak opakuje v konfigurovatelném intervalu.

    Běží jako asyncio úloha na pozadí (spouští ji lifespan v `main.py`). Samotný
    běh retence je synchronní (SQLAlchemy sync session), proto se provádí přes
    `asyncio.to_thread`, aby neblokoval smyčku událostí.

    Každý běh je obalený `try/except`: chyba jednoho běhu se zaloguje a smyčka
    pokračuje dál, nikdy nespadne kvůli jednomu neúspěchu. Interval nikdy
    neklesne pod jednu hodinu, aby špatná konfigurace nezpůsobila těsnou smyčku.

    Úloha se ukončí čistě: `asyncio.CancelledError` z `sleep` nebo `to_thread`
    se propaguje ven (zachytí ji lifespan při zrušení), takže se smyčka zastaví
    okamžitě při vypnutí aplikace.
    """
    interval_seconds = max(settings.retention_interval_hours, 1) * 3600

    while True:
        try:
            result = await asyncio.to_thread(run_retention_once, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Chyba jednoho běhu nesmí shodit smyčku (design.md 9). Zalogujeme
            # a pokračujeme dalším intervalem. Podrobnosti běhu loguje 19.2.
            logger.exception(
                "Běh retence selhal, pokračuji dalším intervalem",
                extra={"event": "retention.run_failed"},
            )
        else:
            # Podrobné logování po kategoriích (kategorie, hranice, počet) dělá
            # `run_retention_once` — viz `_log_run`. Zde už se neloguje, aby
            # nevznikal duplicitní záznam. `result` se nepoužívá, jen potvrzuje
            # úspěšný běh.
            del result

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
