"""Strojové kódy výčtů (database.md sekce 7).

Databáze drží strojové kódy, ne české texty (database.md princip 5). Tento
modul je jediný zdroj pravdy pro tyto kódy v aplikační vrstvě. Mapování na
české popisky je odděleně v `labels.py` (úkol 5.2) — zde záměrně žádné popisky
nejsou.

Balíček `domain` nemá žádné externí závislosti (design.md sekce 1): používá
se jen `enum` ze standardní knihovny. `StrEnum` znamená, že hodnota členu je
přímo strojový kód (`Role.ADMIN == "ADMIN"`), takže se enum přirozeně
porovnává i serializuje proti hodnotám ze sloupců.

Kódy musí přesně odpovídat tabulce v `database.md` sekci 7 a povoleným
hodnotám v modelech (`db/models/`): `ROLE_VALUES`, `ROLE_SOURCE_VALUES`,
`LIFECYCLE_STATE_VALUES`, `CLASSIFICATION_VALUES`,
`CLASSIFICATION_SOURCE_VALUES`, `AUDIT_ACTION_VALUES`.

Výčet `ClassificationSource` je záměrně formulovaný jako rozšiřitelný
(database.md sekce 9): navazující specifikace `classification-advisor` ho
doplní o `AI` a `AI_OVERRIDDEN`. Jádro proto nikde nepředpokládá, že jsou
hodnoty přesně dvě.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Aplikační role uživatele — `users.role` (database.md 7, R2.4)."""

    USER = "USER"
    ADMIN = "ADMIN"


class RoleSource(StrEnum):
    """Původ role — `users.role_source` (database.md 7).

    `LOCAL` = role nastavená lokálně, `IDP` = role přišla z claimu
    poskytovatele identity. Při reálném poskytovateli má claim přednost (R11.6).
    """

    LOCAL = "LOCAL"
    IDP = "IDP"


class LifecycleState(StrEnum):
    """Stav životního cyklu aplikace — `applications.lifecycle_state`.

    Pořadí odpovídá průchodu od návrhu po vyřazení (database.md 7).
    """

    DRAFT = "DRAFT"
    IN_DEVELOPMENT = "IN_DEVELOPMENT"
    TESTING = "TESTING"
    IN_PRODUCTION = "IN_PRODUCTION"
    DECOMMISSIONED = "DECOMMISSIONED"


class Classification(StrEnum):
    """Klasifikace velikosti aplikace — `applications.classification`.

    MALÁ / STŘEDNÍ / VELKÁ v rozhraní; zde jen strojové kódy (database.md 7).
    """

    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class ClassificationSource(StrEnum):
    """Zdroj zápisu klasifikace — `classification_log.source` (database.md 7).

    Rozšiřitelný výčet (database.md 9). Poradce (`classification-advisor`)
    doplnil `AI` (uživatel přijal návrh modelu beze změny úrovně) a
    `AI_OVERRIDDEN` (návrh viděl, ale zvolil jinou úroveň). Jádro nikde
    nepředpokládá, že jsou hodnoty právě dvě.
    """

    HUMAN = "HUMAN"
    AI = "AI"
    AI_OVERRIDDEN = "AI_OVERRIDDEN"
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"


class AuditAction(StrEnum):
    """Typ auditní akce — `audit_log.action` (database.md 7).

    Zahrnuje přihlášení a odhlášení, změny záznamu, zápis a přepis klasifikace,
    vyřazení a návrat, změnu role a zamítnutý pokus o neoprávněnou akci (R8.1).
    Rozšiřitelný výčet (database.md 9).
    """

    SIGN_IN = "SIGN_IN"
    SIGN_OUT = "SIGN_OUT"
    APP_CREATED = "APP_CREATED"
    APP_UPDATED = "APP_UPDATED"
    APP_DECOMMISSIONED = "APP_DECOMMISSIONED"
    APP_REACTIVATED = "APP_REACTIVATED"
    CLASSIFICATION_SET = "CLASSIFICATION_SET"
    CLASSIFICATION_OVERRIDDEN = "CLASSIFICATION_OVERRIDDEN"
    ROLE_CHANGED = "ROLE_CHANGED"
    ACCESS_DENIED = "ACCESS_DENIED"
