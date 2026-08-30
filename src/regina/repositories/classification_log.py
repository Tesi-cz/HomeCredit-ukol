"""Repozitář historie klasifikace — čtení `classification_log` (design.md 6.1).

Detail záznamu (úkol 15.1) zobrazuje historii klasifikace **od nejnovějšího**
(R4.6): pro každý zápis hodnotu, zdroj, aktéra a čas. Tento repozitář drží
jediný dotaz, který tuto historii načte pro jednu aplikaci ve správném pořadí.

**Řazení od nejnovějšího.** Řadí se podle `created_at` sestupně, sekundárně
podle `id` sestupně (log má monotónní `bigint` klíč, database.md 13), aby bylo
pořadí stabilní i u záznamů se shodným časovým razítkem. Využívá se index
`ix_classification_log_application_created` (`application_id, created_at DESC`).

**Aktéři zvlášť.** Řádek logu nese jen `actor_user_id`, ne jméno. Jména aktérů
dohledá routa přes `users.get_by_ids` (jediný dotaz nad množinou identit z
historie), aby se jména držela u adresáře osob a porovnávala se identita, ne
jméno (R2.6). Tento repozitář vrací čisté řádky logu; spojení se jmény je věcí
routy, aby zůstal jednoduchý a testovatelný.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from regina.db.models.classification_log import ClassificationLog


def list_for_application(
    session: Session, application_id: uuid.UUID
) -> list[ClassificationLog]:
    """Vrátí historii klasifikace aplikace od nejnovějšího (R4.6).

    Všechny řádky `classification_log` dané aplikace seřazené sestupně podle
    času zápisu (a sekundárně podle `id`, aby bylo pořadí stabilní). Prázdný
    seznam znamená, že klasifikace nebyla nikdy zapsána — detail pak zobrazí
    prázdný stav historie.
    """
    stmt = (
        select(ClassificationLog)
        .where(ClassificationLog.application_id == application_id)
        .order_by(ClassificationLog.created_at.desc(), ClassificationLog.id.desc())
    )
    return list(session.execute(stmt).scalars().all())
