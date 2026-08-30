"""Validační modely formuláře pro vznik a editaci záznamu (úkol 14.1, R5).

Validace vstupu formuláře **na backendu** (R5.4, design.md 8). Validace
v prohlížeči je jen pohodlnost — autoritativní je to, co projde tudy. Modul má
dvě odpovědnosti a záměrně je drží oddělené:

1. **Tvar a výčty bez databáze** — pydantic model ``ApplicationForm``. Ověří
   povinná pole (R5.2, R5.3) a to, že stav, klasifikace a útvar nesou jen
   povolenou hodnotu (R5.4). Tyhle kontroly nepotřebují session, takže běží
   jako čistý model a dají se testovat bez databáze.

2. **Kontroly proti databázi** — ``validate_uniqueness_and_refs`` s otevřenou
   session. Unikátnost názvu bez ohledu na velikost písmen (R5.8) a existence
   odkazovaných osob (odpovědná trojice, R2.6) vyžadují dotaz, proto stojí
   samostatně. Vytvoření (bez ``exclude_id``) i editace (s ``exclude_id``
   upravovaného záznamu) sdílejí tutéž funkci.

**Proč rozdělené a ne jeden pydantic validátor se session.** Balíček ``domain``
i tvarová validace mají zůstat bez databáze (design.md sekce 1). Míchat dotaz do
pydantic validátoru by svázalo tvar formuláře s DB a znemožnilo čistý test.
Služba (úkol 14.2) a routy (14.3/14.4) proto zavolají nejdřív ``ApplicationForm``
na tvar, pak ``validate_uniqueness_and_refs`` na kolize — a spojí chyby.

**Struktura chyb pro šablonu.** Obě cesty vracejí chyby jako mapu
``{název_pole: [hlášky]}`` (``FieldErrors``). Průvodce (úkol 14.3) tak vykreslí
chybu **u konkrétního pole**, ne jako jednu hlášku (R5.3, ui.md sekce 6). Klíče
polí jsou konstanty ``FIELD_*`` níže, aby se šablona i validace odkazovaly na
tentýž řetězec.

**Povinnost polí (R5.2).** Povinné: název, vlastník, technický správce, útvar,
stav. Nepovinné: zástupce, popis, AI model, klasifikace (R5.7 — záznam smí
vzniknout neklasifikovaný). Prázdný nebo jen-mezerový řetězec u povinného pole
je „chybí" (R5.3).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from regina.domain.enums import Classification, LifecycleState
from regina.repositories import applications as applications_repo
from regina.repositories import users as users_repo

# --- Názvy polí formuláře (jediný zdroj pravdy pro šablonu i validaci) ---
FIELD_NAME = "name"
FIELD_DESCRIPTION = "description"
FIELD_DEPARTMENT = "department"
FIELD_OWNER = "owner_user_id"
FIELD_DEPUTY = "deputy_user_id"
FIELD_TECH_ADMIN = "tech_admin_user_id"
FIELD_LIFECYCLE_STATE = "lifecycle_state"
FIELD_AI_MODEL = "ai_model"
FIELD_CLASSIFICATION = "classification"

#: Mapa chyb: pole → seznam českých hlášek. Šablona ji čte po polích (R5.3).
FieldErrors = dict[str, list[str]]


class FormValidationError(Exception):
    """Formulář neprošel validací. Nese chyby po polích pro vykreslení.

    Vyhazuje ji ``ApplicationForm.parse`` (tvarové chyby) a smí ji použít i
    volající po ``validate_uniqueness_and_refs``. ``errors`` je mapa
    ``{pole: [hlášky]}`` (viz ``FieldErrors``), kterou průvodce vykreslí u
    konkrétních polí, ne jako jednu souhrnnou hlášku (ui.md sekce 6).
    """

    def __init__(self, errors: FieldErrors) -> None:
        self.errors: FieldErrors = errors
        super().__init__("Formulář obsahuje chyby validace.")


def _clean_optional(value: str | None) -> str | None:
    """Ořízne mezery; prázdný řetězec převede na ``None`` (nepovinné pole)."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class ApplicationForm(BaseModel):
    """Ověřený tvar formuláře záznamu — povinná pole a výčty (R5.2–5.4).

    Bez databáze: kontroluje jen tvar vstupu. Unikátnost názvu a existenci osob
    řeší ``validate_uniqueness_and_refs`` se session. Textová pole se ořezávají
    od mezer; prázdné nepovinné se ukládá jako ``None`` (R5.7 — neklasifikováno,
    zástupce nepovinný).

    Výčty jsou typované (``LifecycleState``, ``Classification``); útvar je prostý
    text ověřený proti konfigurovanému seznamu ve validátoru — jeho povolené
    hodnoty žijí v konfiguraci, ne ve výčtu.
    """

    model_config = ConfigDict(str_strip_whitespace=False, extra="ignore")

    name: str
    department: str
    owner_user_id: uuid.UUID
    tech_admin_user_id: uuid.UUID
    lifecycle_state: LifecycleState
    deputy_user_id: uuid.UUID | None = None
    description: str | None = None
    ai_model: str | None = None
    classification: Classification | None = None

    @field_validator("name", "department", mode="before")
    @classmethod
    def _required_text_present(cls, value: object) -> object:
        """Povinné textové pole nesmí být prázdné ani jen mezery (R5.3)."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("Toto pole je povinné.")
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", "ai_model", mode="before")
    @classmethod
    def _optional_text(cls, value: object) -> object:
        """Nepovinný text: prázdný nebo jen mezery → ``None``."""
        if isinstance(value, str):
            return _clean_optional(value)
        return value

    @field_validator("deputy_user_id", "classification", mode="before")
    @classmethod
    def _blank_optional_to_none(cls, value: object) -> object:
        """Prázdný výběr nepovinného pole (``""``) se čte jako nevyplněno."""
        if isinstance(value, str) and not value.strip():
            return None
        return value


# --- České hlášky pro tvarové chyby pydantiku ---
# Pydantic hlásí chyby anglicky; do rozhraní ale nesmí anglický text (R13.11).
# Překlad je podle typu chyby a pole. Klíče odpovídají `type` z pydantic v2.

_REQUIRED_MESSAGES: Mapping[str, str] = {
    FIELD_NAME: "Zadejte název aplikace.",
    FIELD_DEPARTMENT: "Vyberte útvar.",
    FIELD_OWNER: "Vyberte vlastníka.",
    FIELD_TECH_ADMIN: "Vyberte technického správce.",
    FIELD_LIFECYCLE_STATE: "Vyberte stav.",
}

_ENUM_MESSAGES: Mapping[str, str] = {
    FIELD_LIFECYCLE_STATE: "Neplatný stav — vyberte jednu z nabízených hodnot.",
    FIELD_CLASSIFICATION: "Neplatná klasifikace — vyberte jednu z nabízených hodnot.",
    FIELD_OWNER: "Neplatný odkaz na vlastníka.",
    FIELD_TECH_ADMIN: "Neplatný odkaz na technického správce.",
    FIELD_DEPUTY: "Neplatný odkaz na zástupce.",
}

_FALLBACK_MESSAGE = "Neplatná hodnota."


def _czech_message_for(field: str, error_type: str) -> str:
    """Přeloží pydantic chybu na českou hlášku podle pole a typu chyby."""
    # Chybějící / prázdná povinná hodnota.
    if error_type in {"missing", "value_error"} and field in _REQUIRED_MESSAGES:
        return _REQUIRED_MESSAGES[field]
    if error_type in {"missing", "string_type", "uuid_type", "uuid_parsing"}:
        return _REQUIRED_MESSAGES.get(field, _ENUM_MESSAGES.get(field, _FALLBACK_MESSAGE))
    # Neplatná hodnota výčtu (stav/klasifikace) — strojový kód mimo povolený seznam.
    if error_type == "enum" and field in _ENUM_MESSAGES:
        return _ENUM_MESSAGES[field]
    if field in _ENUM_MESSAGES:
        return _ENUM_MESSAGES[field]
    if field in _REQUIRED_MESSAGES:
        return _REQUIRED_MESSAGES[field]
    return _FALLBACK_MESSAGE


def _collect_pydantic_errors(error: ValidationError) -> FieldErrors:
    """Přemapuje pydantic ValidationError na mapu ``{pole: [české hlášky]}``."""
    errors: FieldErrors = defaultdict(list)
    for issue in error.errors():
        loc = issue.get("loc") or ()
        field = str(loc[0]) if loc else "_"
        message = _czech_message_for(field, str(issue.get("type", "")))
        if message not in errors[field]:
            errors[field].append(message)
    return dict(errors)


def parse_application_form(
    raw: Mapping[str, object],
    allowed_departments: tuple[str, ...],
) -> ApplicationForm:
    """Ověří tvar formuláře; při chybě vyhodí ``FormValidationError``.

    Dvoustupňová tvarová validace bez databáze:

    1. **Pydantic** ověří povinnost a typy včetně výčtů stavu a klasifikace
       (R5.2, R5.3, R5.4). Anglické chyby se přeloží do češtiny po polích.
    2. **Útvar proti konfiguraci** — útvar je uzavřený výčet v konfiguraci
       (config ``DEPARTMENTS``), ne ve výčtu ``enums.py``. Hodnota mimo
       ``allowed_departments`` se odmítne, i kdyby prohlížeč nabízel jen platné
       (R5.4 — strojové kódy mimo povolený seznam se nikdy nedůvěřuje).

    Vrací ověřený ``ApplicationForm``. Kolize názvu a existenci osob řeší
    následně ``validate_uniqueness_and_refs`` se session.
    """
    try:
        form = ApplicationForm.model_validate(dict(raw))
    except ValidationError as error:
        raise FormValidationError(_collect_pydantic_errors(error)) from error

    # Útvar: povolený seznam žije v konfiguraci, ne ve výčtu. Nedůvěřujeme
    # klientovi ani zde (R5.4).
    if form.department not in allowed_departments:
        raise FormValidationError(
            {FIELD_DEPARTMENT: ["Neplatný útvar — vyberte jeden z nabízených."]}
        )

    return form


def validate_uniqueness_and_refs(
    session: Session,
    form: ApplicationForm,
    exclude_id: uuid.UUID | None = None,
) -> FieldErrors:
    """Kontroly, které potřebují databázi: unikátní název a existence osob.

    Volá se **po** ``parse_application_form`` s ověřeným tvarem. Vrací mapu chyb
    po polích (prázdná = bez kolizí); volající ji spojí s případnými tvarovými
    chybami a při neprázdné mapě formulář vrátí uživateli (design.md 8).

    - **Unikátní název (R5.8).** ``applications_repo.name_exists`` porovná
      ``lower(name)``. Při vytvoření ``exclude_id=None``; při editaci se předá
      ``id`` upravovaného záznamu, aby uložení beze změny názvu neselhalo na
      kolizi samo se sebou.
    - **Existence osob (R2.6).** Vlastník a technický správce musí odkazovat na
      aktivní osobu; zástupce jen pokud je vyplněn. Osoby se vybírají z adresáře
      podle identity, ne psaním jména (ui.md sekce 6) — kdyby přišel neznámý
      identifikátor, odmítne se s hláškou u pole dřív, než na něj narazí cizí
      klíč ``ON DELETE RESTRICT``.

    Nevyhazuje výjimku — vrací chyby, aby je volající mohl spojit s tvarovými.
    """
    errors: FieldErrors = defaultdict(list)

    if applications_repo.name_exists(session, form.name, exclude_id=exclude_id):
        errors[FIELD_NAME].append("Aplikace s tímto názvem už existuje.")

    if not users_repo.active_id_exists(session, form.owner_user_id):
        errors[FIELD_OWNER].append("Vybraný vlastník neexistuje nebo není aktivní.")

    if not users_repo.active_id_exists(session, form.tech_admin_user_id):
        errors[FIELD_TECH_ADMIN].append(
            "Vybraný technický správce neexistuje nebo není aktivní."
        )

    if form.deputy_user_id is not None and not users_repo.active_id_exists(
        session, form.deputy_user_id
    ):
        errors[FIELD_DEPUTY].append("Vybraný zástupce neexistuje nebo není aktivní.")

    return dict(errors)
