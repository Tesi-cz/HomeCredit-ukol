"""Aplikační pojistka nemazatelnosti auditu (R8.5, database.md sekce 6, design.md 5.2).

Auditní tabulka je přírůstková: aplikace nad ní **nikdy** nevydá `UPDATE`
ani `DELETE`. Jediná povolená výjimka je retenční rutina (úkol 19.1), která
maže záznamy za retenční hranicí. Tohle je pravidlo aplikace, ne struktury —
proto se vynucuje ve vrstvě, která do databáze zapisuje.

**Jak to funguje.** Na `Session` visí posluchač události `before_flush`.
Před každým flushem projde, co session chystá zapsat, a pokud narazí na
`AuditLog`, který má být **změněn** (`dirty`) nebo **smazán** (`deleted`),
vyhodí `AuditImmutableError` — dřív, než se dotyčné SQL vůbec pošle do
databáze. Vkládání nových záznamů (`new`) je vždy povolené; přírůstek je celý
smysl auditu. Ostatní tabulky (applications, users, …) posluchač nezajímají.

**Výjimka pro retenci.** Retenční rutina (úkol 19.1) je jediné místo, které
smí auditní řádky mazat. Aby nemusela obcházet pojistku, obalí své mazání do
kontextového správce `audit_retention_context(session)`. Ten na dobu svého
běhu nastaví v `session.info` úzce mířený příznak, který posluchač respektuje
jen pro **mazání** (retence nikdy nic needituje). Nic jiného v aplikaci tento
příznak nenastavuje.

Posluchač se registruje jednou při startu (`db/session.py` → `init_engine`),
takže je aktivní v běžící aplikaci i v testech, které session inicializují
stejnou cestou.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.orm import Session

from regina.db.models.audit_log import AuditLog

# Klíč v `session.info`, kterým retenční rutina povoluje mazání auditních
# řádků. Záměrně privátní a dokumentovaný jen zde — jiný kód ho nesmí sahat.
_RETENTION_FLAG = "regina.audit_retention_delete"


class AuditImmutableError(RuntimeError):
    """Pokus o `UPDATE`/`DELETE` auditního záznamu mimo retenční rutinu (R8.5).

    Značí programátorskou chybu: auditní log je přírůstkový a jedinou cestou,
    jak z něj řádky odstranit, je retence přes `audit_retention_context`.
    """


@contextmanager
def audit_retention_context(session: Session) -> Iterator[None]:
    """Povolí mazání auditních řádků po dobu běhu bloku (jen pro retenci, R8.5).

    Toto je **jediná** povolená výjimka z nemazatelnosti auditu. Retenční
    rutina (úkol 19.1) obalí svůj `DELETE` nad `audit_log` tímto správcem;
    nic jiného ho volat nemá. Příznak platí pouze pro `DELETE` — editaci
    auditního záznamu pojistka odmítne i uvnitř tohoto bloku, protože retence
    záznamy jen maže, nikdy neupravuje.

    Příznak se drží v `session.info`, takže je vázaný na konkrétní session a po
    opuštění bloku se vždy uklidí, i když retence vyhodí výjimku.
    """
    previous = session.info.get(_RETENTION_FLAG, False)
    session.info[_RETENTION_FLAG] = True
    try:
        yield
    finally:
        session.info[_RETENTION_FLAG] = previous


def _retention_delete_allowed(session: Session) -> bool:
    return bool(session.info.get(_RETENTION_FLAG, False))


def _before_flush(session: Session, flush_context: object, instances: object) -> None:
    """Odmítne změnu nebo smazání auditního záznamu mimo retenci (R8.5).

    `session.dirty` jsou objekty s neuloženými změnami (chystaný `UPDATE`),
    `session.deleted` objekty určené ke smazání (chystaný `DELETE`). Nové
    záznamy (`session.new`) se nekontrolují — vkládání je vždy povolené.
    """
    # Editace auditního záznamu není povolená nikdy, ani při retenci.
    for obj in session.dirty:
        if isinstance(obj, AuditLog) and session.is_modified(obj):
            raise AuditImmutableError(
                "Auditní záznam nelze editovat — audit_log je přírůstkový (R8.5)."
            )

    # Mazání je povolené jen retenční rutině přes audit_retention_context.
    if _retention_delete_allowed(session):
        return
    for obj in session.deleted:
        if isinstance(obj, AuditLog):
            raise AuditImmutableError(
                "Auditní záznam nelze smazat mimo retenční rutinu "
                "(použij audit_retention_context) — audit_log je přírůstkový (R8.5)."
            )


def install_audit_immutability_guard() -> None:
    """Zaregistruje pojistku na všechny `Session` (idempotentně).

    Volá se při startu z `db/session.py` (`init_engine`). Registrace na třídě
    `Session` platí pro všechny sessions z fabriky. Opakované volání nic
    nezdvojí — před přidáním posluchače se ověří, že ještě není připojený.
    """
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
