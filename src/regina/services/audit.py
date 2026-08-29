"""Auditní zápis (design.md 5.2, R8).

Tohle je **jediné** místo, kde vzniká auditní záznam. Služby sem zapisují ve
**stejné transakci** jako změnu, kterou zaznamenávají. Audit ve stejné
transakci je záměr: nemůže vzniknout změna bez auditního záznamu ani naopak
(design.md 5.2). O commit se stará vrstva, která `record` volá — funkce sama
transakci neuzavírá (design.md 6.3).

**Snapshot aktéra.** Ukládá se kopie jména a e-mailu aktéra pořízená v okamžiku
akce (R8.3), aby záznam zůstal čitelný, i když je osoba později odebrána
z adresáře.

**Co se neukládá.** `changed_fields` obsahuje jen **názvy** změněných atributů,
nikdy hodnoty — jinak by se do auditu dostaly osobní údaje z odpovědné trojice
(R8.6, R12.10). Aby se hodnota nedostala do auditu ani omylem, `record` přijímá
výhradně posloupnost názvů (`Sequence[str]`); předání mapy hodnot skončí
`TypeError`, ne tichým zápisem osobních údajů. Žádná IP adresa ani user agent
(R8.6).

**Jádro a obálky.** Autoritativní zapisovač je jediná funkce `record`. Pro
běžné akce jsou nad ní tenké pojmenované obálky (`sign_in`, `sign_out`,
`app_created`, …), které jen doplní správnou `AuditAction` a typ entity; každá
z nich volá `record`, žádná nepíše do session sama. Volající tak nemusí sahat
na výčet akcí a přitom existuje jen jedno místo, které skládá `AuditLog`.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from regina.db.models.audit_log import AuditLog
from regina.domain.enums import AuditAction

# Typy entit, na které audit odkazuje (audit_log.AUDIT_ENTITY_TYPE_VALUES).
ENTITY_APPLICATION = "APPLICATION"
ENTITY_USER = "USER"
ENTITY_SESSION = "SESSION"


@runtime_checkable
class AuditActor(Protocol):
    """Strukturální typ aktéra pro auditní zápis.

    Stačí identita (`id`, může být `None` u neúspěšného přihlášení), jméno
    a e-mail pro snapshot. Splňuje ho ORM `User` i `CurrentUser` z `auth/deps`
    (má `id`, `email`, `name`).
    """

    id: object
    email: object
    name: object


def record(
    session: Session,
    actor: AuditActor | None,
    action: AuditAction,
    *,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    summary: str = "",
    changed_fields: Sequence[str] | None = None,
) -> AuditLog:
    """Zapíše auditní záznam do právě probíhající transakce.

    Jediný autoritativní zapisovač auditu. Neprovádí commit — o transakci se
    stará vrstva, která `record` volá (design.md 5.2, 6.3), takže auditní
    záznam a změna, kterou popisuje, se potvrdí atomicky. Vrací vytvořený
    záznam pro případné navázání v testech.

    `actor` může být `None` (např. zamítnutý nebo neúspěšný pokus bez
    identifikované osoby); pak se snapshot aktéra neplní.

    `changed_fields` smí obsahovat **jen názvy** atributů (R8.6, R12.10).
    Předání mapy hodnot je programátorská chyba a skončí `TypeError` —
    hodnoty se do auditu nesmějí dostat ani omylem.
    """
    actor_user_id = _as_uuid(getattr(actor, "id", None)) if actor is not None else None
    actor_email = _as_optional_str(getattr(actor, "email", None)) if actor else None
    actor_display_name = _as_optional_str(getattr(actor, "name", None)) if actor else None

    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        actor_display_name=actor_display_name,
        action=str(action),
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        # Jen názvy změněných atributů, nikdy hodnoty (R8.6, R12.10).
        changed_fields=_field_names(changed_fields),
    )
    session.add(entry)
    return entry


# -- Pojmenované obálky nad jádrem ---------------------------------------
#
# Každá obálka jen doplní `AuditAction` a typ entity a zavolá `record`. Žádná
# z nich nepíše do session přímo — jediný zapisovač zůstává `record`.


def sign_in(session: Session, actor: AuditActor | None) -> AuditLog:
    """Audit přihlášení (R8.1). Entita je session."""
    return record(
        session,
        actor,
        AuditAction.SIGN_IN,
        entity_type=ENTITY_SESSION,
        summary="Přihlášení uživatele.",
    )


def sign_out(session: Session, actor: AuditActor | None) -> AuditLog:
    """Audit odhlášení (R8.1, R1.8). Entita je session."""
    return record(
        session,
        actor,
        AuditAction.SIGN_OUT,
        entity_type=ENTITY_SESSION,
        summary="Odhlášení uživatele.",
    )


def access_denied(
    session: Session,
    actor: AuditActor | None,
    *,
    summary: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> AuditLog:
    """Audit zamítnutého pokusu o neoprávněnou akci (R8.1, R2.3).

    `summary` popisuje pokus česky; `entity_type`/`entity_id` cíl, pokud je
    znám. Volá jediný handler `AuthorizationError` (`auth/deps.py`).
    """
    return record(
        session,
        actor,
        AuditAction.ACCESS_DENIED,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
    )


def app_created(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
    changed_fields: Sequence[str] | None = None,
) -> AuditLog:
    """Audit vytvoření záznamu aplikace (R8.1, R5.9)."""
    return record(
        session,
        actor,
        AuditAction.APP_CREATED,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
        changed_fields=changed_fields,
    )


def app_updated(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
    changed_fields: Sequence[str] | None = None,
) -> AuditLog:
    """Audit editace záznamu aplikace (R8.1, R5.9). `changed_fields` = názvy."""
    return record(
        session,
        actor,
        AuditAction.APP_UPDATED,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
        changed_fields=changed_fields,
    )


def app_decommissioned(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
) -> AuditLog:
    """Audit vyřazení záznamu do stavu `Vyřazená` (R8.1, R5.13)."""
    return record(
        session,
        actor,
        AuditAction.APP_DECOMMISSIONED,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
    )


def app_reactivated(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
) -> AuditLog:
    """Audit návratu záznamu ze stavu `Vyřazená` (R8.1, R5.14)."""
    return record(
        session,
        actor,
        AuditAction.APP_REACTIVATED,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
    )


def classification_set(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
) -> AuditLog:
    """Audit zápisu klasifikace na vlastní záznam (R8.1, R6.9)."""
    return record(
        session,
        actor,
        AuditAction.CLASSIFICATION_SET,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
    )


def classification_overridden(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
) -> AuditLog:
    """Audit přepisu klasifikace správcem (R8.1, R7.7)."""
    return record(
        session,
        actor,
        AuditAction.CLASSIFICATION_OVERRIDDEN,
        entity_type=ENTITY_APPLICATION,
        entity_id=entity_id,
        summary=summary,
    )


def role_changed(
    session: Session,
    actor: AuditActor | None,
    *,
    entity_id: uuid.UUID,
    summary: str,
) -> AuditLog:
    """Audit změny role osoby (R8.1, R11.4). Entita je dotčený uživatel."""
    return record(
        session,
        actor,
        AuditAction.ROLE_CHANGED,
        entity_type=ENTITY_USER,
        entity_id=entity_id,
        summary=summary,
    )


# -- Pomocné převody -----------------------------------------------------


def _field_names(changed_fields: Sequence[str] | None) -> list[str] | None:
    """Ověří a znormalizuje seznam názvů změněných atributů.

    Do auditu smějí jen **názvy** atributů, ne hodnoty (R8.6, R12.10). Mapa
    (typicky `{"pole": hodnota}`) je proto odmítnuta `TypeError` — jinak by se
    do auditu dostaly osobní údaje z odpovědné trojice. Řetězec se také odmítá:
    jednotlivé znaky nejsou názvy polí a šlo by skoro jistě o chybu volajícího.
    """
    if changed_fields is None:
        return None
    if isinstance(changed_fields, Mapping):
        raise TypeError(
            "changed_fields musí být posloupnost názvů atributů, ne mapa hodnot "
            "— do auditu se nikdy nesmějí zapsat hodnoty (R8.6, R12.10)."
        )
    if isinstance(changed_fields, (str, bytes)):
        raise TypeError(
            "changed_fields musí být posloupnost názvů atributů, ne jeden řetězec."
        )
    names = [str(name) for name in changed_fields]
    if any(not name for name in names):
        raise ValueError("changed_fields nesmí obsahovat prázdný název atributu.")
    return names or None


def _as_uuid(value: object) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None
