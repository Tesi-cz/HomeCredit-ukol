"""Autorizační pravidla jako čisté funkce (design.md sekce 4.3).

Toto je jádro celého bezpečnostního návrhu. Každá funkce odpovídá jednomu
řádku capability matrix z R2 a vrací pouze `bool` — rozhoduje, zda daný aktér
smí danou schopnost použít. Vynucení (403, audit `ACCESS_DENIED`) je věcí
vrstvy `auth` a `web`; tady se jen říká „ano/ne".

**Jedno pravidlo, dvě použití** (design.md 4.3). Tytéž funkce volá FastAPI
guard *před* operací (vynucení, R2.2) i šablona při rozhodování, zda vykreslit
tlačítko (pohodlnost, R2.5). Rozhraní se proto nemůže rozejít s vynucením.

**Bez závislostí** (design.md sekce 1). Balíček `domain` nesmí znát databázi,
HTTP ani FastAPI. Funkce proto nepřebírají ORM entity, ale cokoli, co splní
strukturální protokoly `Actor` a `AppRecord` níže (duck typing přes
`typing.Protocol`). Díky tomu jsou testovatelné bez databáze a bez HTTP
(úkol 5.4) — v testu stačí lehký objekt s atributy `id` a `role`.

**Porovnávají se identifikátory, nikdy jména** (R2.6). Členství v odpovědné
trojici se ověřuje proti `owner_user_id`, `deputy_user_id` a
`tech_admin_user_id`, tedy proti identitě osoby, ne proti zobrazovanému jménu.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from regina.domain.enums import Role


@runtime_checkable
class Actor(Protocol):
    """Strukturální typ přihlášeného aktéra.

    Cokoli s identitou (`id`) a aplikační rolí (`role`) je použitelné —
    ORM `User`, položka session i testovací dvojník. Role se porovnává proti
    `Role.ADMIN`; `role` proto může být `Role`, nebo její strojová hodnota
    `"ADMIN"` (StrEnum se porovnává i proti řetězci).
    """

    id: object
    role: object


@runtime_checkable
class AppRecord(Protocol):
    """Strukturální typ záznamu registru pro účely autorizace.

    Zajímá nás jen odpovědná trojice — identifikátory osob, ne jména (R2.6).
    `deputy_user_id` může být prázdný (zástupce není povinný, database.md 4).
    """

    owner_user_id: object
    deputy_user_id: object | None
    tech_admin_user_id: object


def _is_admin(actor: Actor) -> bool:
    """Aktér má aplikační roli Admin.

    Porovnává se proti hodnotě `Role.ADMIN`. Díky `StrEnum` projde jak
    `Role.ADMIN`, tak holý řetězec `"ADMIN"`.
    """
    return actor.role == Role.ADMIN


def _is_trio_member(actor: Actor, app: AppRecord) -> bool:
    """Aktér je členem odpovědné trojice záznamu.

    Porovnávají se **identifikátory osob**, nikdy jména (R2.6). Prázdná pole
    (chybějící zástupce) se nesmí shodovat s `None` identitou aktéra, proto se
    kandidáti bez hodnoty vynechávají.
    """
    trio = (app.owner_user_id, app.deputy_user_id, app.tech_admin_user_id)
    return any(member_id is not None and actor.id == member_id for member_id in trio)


def can_edit(actor: Actor, app: AppRecord) -> bool:
    """Smí aktér editovat záznam? (matrix: editace záznamu)

    Povoleno členům odpovědné trojice u vlastního záznamu a vždy roli Admin
    (matrix řádky „Editovat záznam, kde je / není členem", R5.10). Rozhodnutí
    stojí na porovnání identit, ne jmen (R2.6).
    """
    return _is_admin(actor) or _is_trio_member(actor, app)


def can_set_classification(actor: Actor, app: AppRecord) -> bool:
    """Smí aktér nastavit klasifikaci záznamu? (matrix: nastavit klasifikaci)

    Stejné pravidlo členství jako editace: člen trojice smí zapsat klasifikaci
    svého záznamu, Admin kdekoli (matrix „Nastavit Classification, kde je
    členem" + řádek Admin). Přepis *cizího* záznamu je samostatná schopnost —
    viz `can_override_classification`.
    """
    return _is_admin(actor) or _is_trio_member(actor, app)


def can_override_classification(actor: Actor) -> bool:
    """Smí aktér přepsat klasifikaci cizího záznamu? (matrix: změnit u cizího)

    Vyhrazeno roli Admin (R7.1, R7.6). Nezávisí na konkrétním záznamu —
    přepis je definičně zásah do záznamu, kde aktér není členem trojice,
    a povinný důvod řeší vrstva služeb a `CHECK` v databázi (R7.2, R7.3).
    """
    return _is_admin(actor)


def can_decommission(actor: Actor) -> bool:
    """Smí aktér vyřadit záznam? (matrix: nastavit stav `Vyřazená`)

    Vyhrazeno roli Admin (R5.12). Zamítá se i členům trojice, protože vyřazení
    spouští budoucí fyzické smazání záznamu retenční rutinou (design.md 5.3).
    """
    return _is_admin(actor)


def can_read_audit(actor: Actor) -> bool:
    """Smí aktér číst auditní log? (matrix: číst Audit_Log)

    Vyhrazeno roli Admin (R8.4).
    """
    return _is_admin(actor)


def can_export(actor: Actor) -> bool:
    """Smí aktér exportovat CSV? (matrix: exportovat CSV)

    Vyhrazeno roli Admin — registru i auditu (R10.1, R10.2, R10.4).
    """
    return _is_admin(actor)


def can_manage_roles(actor: Actor) -> bool:
    """Smí aktér spravovat přiřazení rolí? (matrix: spravovat role)

    Vyhrazeno roli Admin (R11.2).
    """
    return _is_admin(actor)
