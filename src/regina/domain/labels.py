"""České popisky ke strojovým kódům výčtů (R13.1, R13.11).

Databáze i aplikační vrstva pracují se strojovými kódy z `enums.py`
(database.md princip 5). Do rozhraní ale nesmí proniknout žádný strojový
kód ani anglický popisek (R13.11 — „SHALL NOT display any English label").
Tento modul je jediné místo, kde se strojový kód překládá na český text.

Rozdělení odpovědnosti je záměrné a zrcadlí `enums.py`:

- `enums.py` — strojové kódy, žádný český text (co je v databázi),
- `labels.py` — český text, žádná databázová logika (co vidí uživatel).

Mapování musí být vyčerpávající: každý člen každého výčtu z `enums.py` má
popisek. Kdyby některý chyběl, unikl by do rozhraní strojový kód a porušil
by R13.11. Test na konci úkolu ověřuje, že žádný klíč nechybí.

Balíček `domain` nemá žádné externí závislosti (design.md sekce 1): tento
modul používá jen `enums` ze stejného balíčku a standardní knihovnu.

Zdroje popisků:

- Classification, Lifecycle_State — Glossary v `requirements.md`
  (`MALÁ`/`STŘEDNÍ`/`VELKÁ`; `Návrh` → `Ve vývoji` → `Testování` →
  `Produkce` → `Vyřazená`),
- Classification_Source — Glossary (`HUMAN` = zadal člověk odpovědný za
  záznam, `ADMIN_OVERRIDE` = přepis roli Admin), zobrazuje se v detailu
  u klasifikace (R4.4) a v historii (R4.6),
- role a jejich původ — Glossary (Role_User / Role_Admin, `LOCAL` / `IDP`),
- auditní akce — Requirement 8 (přihlášení, odhlášení, změny záznamu,
  klasifikace, role, zamítnutý přístup),
- `NO_CLASSIFICATION` — stav bez klasifikace (R2.7, R3.8), v rozhraní
  „Neklasifikováno".
"""

from __future__ import annotations

from enum import StrEnum

from regina.domain.enums import (
    AuditAction,
    Classification,
    ClassificationSource,
    LifecycleState,
    Role,
    RoleSource,
)

#: Popisek pro záznam bez platné klasifikace (R2.7, R3.8). Není to člen
#: výčtu `Classification` — absence klasifikace je stav „žádná hodnota",
#: ne další úroveň. Rozhraní ho ukazuje tam, kde jiné záznamy mají badge
#: s úrovní.
NO_CLASSIFICATION_LABEL = "Neklasifikováno"


CLASSIFICATION_LABELS: dict[Classification, str] = {
    Classification.SMALL: "MALÁ",
    Classification.MEDIUM: "STŘEDNÍ",
    Classification.LARGE: "VELKÁ",
}


LIFECYCLE_STATE_LABELS: dict[LifecycleState, str] = {
    LifecycleState.DRAFT: "Návrh",
    LifecycleState.IN_DEVELOPMENT: "Ve vývoji",
    LifecycleState.TESTING: "Testování",
    LifecycleState.IN_PRODUCTION: "Produkce",
    LifecycleState.DECOMMISSIONED: "Vyřazená",
}


CLASSIFICATION_SOURCE_LABELS: dict[ClassificationSource, str] = {
    ClassificationSource.HUMAN: "Člověk",
    ClassificationSource.ADMIN_OVERRIDE: "Přepis správce",
}


ROLE_LABELS: dict[Role, str] = {
    Role.USER: "Uživatel",
    Role.ADMIN: "Správce",
}


ROLE_SOURCE_LABELS: dict[RoleSource, str] = {
    RoleSource.LOCAL: "Lokální",
    RoleSource.IDP: "Z poskytovatele identity",
}


AUDIT_ACTION_LABELS: dict[AuditAction, str] = {
    AuditAction.SIGN_IN: "Přihlášení",
    AuditAction.SIGN_OUT: "Odhlášení",
    AuditAction.APP_CREATED: "Vytvoření záznamu",
    AuditAction.APP_UPDATED: "Úprava záznamu",
    AuditAction.APP_DECOMMISSIONED: "Vyřazení záznamu",
    AuditAction.APP_REACTIVATED: "Návrat záznamu z vyřazení",
    AuditAction.CLASSIFICATION_SET: "Zápis klasifikace",
    AuditAction.CLASSIFICATION_OVERRIDDEN: "Přepis klasifikace",
    AuditAction.ROLE_CHANGED: "Změna role",
    AuditAction.ACCESS_DENIED: "Zamítnutý přístup",
}


#: Sjednocené vyhledání pro `label()`. Klíčem je člen výčtu (`StrEnum` má
#: unikátní identitu podle typu i hodnoty, takže se různé výčty nekříží).
_ALL_LABELS: dict[StrEnum, str] = {
    **CLASSIFICATION_LABELS,
    **LIFECYCLE_STATE_LABELS,
    **CLASSIFICATION_SOURCE_LABELS,
    **ROLE_LABELS,
    **ROLE_SOURCE_LABELS,
    **AUDIT_ACTION_LABELS,
}


def label(value: StrEnum) -> str:
    """Vrátí český popisek pro člen některého výčtu z `enums.py`.

    Jednotný vstupní bod pro rozhraní, aby se strojový kód nikde nezobrazil
    přímo (R13.11). Pokrývá všechny členy `Classification`, `LifecycleState`,
    `ClassificationSource`, `Role`, `RoleSource` a `AuditAction`.

    Pro záznam bez klasifikace se nepředává člen výčtu (žádný takový není) —
    použije se přímo `NO_CLASSIFICATION_LABEL`, viz `classification_label`.

    Vyhazuje `KeyError`, pokud pro hodnotu popisek chybí. To je záměr: chybějící
    popisek je chyba v tomto modulu, ne stav, který by se měl tiše přejít
    zobrazením strojového kódu.
    """
    return _ALL_LABELS[value]


def classification_label(value: Classification | None) -> str:
    """Popisek klasifikace včetně stavu bez klasifikace (R2.7, R3.8).

    Pro `None` (záznam dosud nemá klasifikaci) vrací `NO_CLASSIFICATION_LABEL`,
    jinak český popisek úrovně. Rozhraní tak má jediné volání pro obě situace.
    """
    if value is None:
        return NO_CLASSIFICATION_LABEL
    return CLASSIFICATION_LABELS[value]
