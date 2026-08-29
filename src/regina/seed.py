"""Naplnění databáze syntetickými daty (design.md sekce 14, R12.9, R12.11).

Registr nesmí být při hodnocení prázdný, proto se při startu volitelně naplní
vymyšlenými daty. Modul řeší dvě vrstvy dat, které na sobě závisí:

- **osoby** (úkol 9.1) — adresář `users`, odpovědná trojice u aplikací na ně
  odkazuje;
- **aplikace a historie klasifikace** (úkol 9.2) — záznamy `applications`
  napříč všemi útvary, stavy a klasifikacemi, u části s historií v
  `classification_log`. Staví se na osobách, proto se seedují až po nich.

Zásady (design.md 14):

- **Vše je syntetické.** Žádné skutečné jméno, e-mail ani telefon. Doména
  `@regina.local` neexistuje, takže na ni nelze nic doručit.
- **Idempotence.** Opakovaný start data nezduplikuje. U osob je klíčem e-mail
  bez ohledu na velikost písmen (`uq_users_lower_email`), u aplikací název bez
  ohledu na velikost písmen (`uq_applications_lower_name`, database.md 12). Když
  osoba/aplikace s daným klíčem už existuje, přeskočí se a ponechá beze změny —
  a u aplikace se pak **nepřidá ani její historie klasifikace**, takže log
  řádky nenarůstají při každém startu.
- **Řízeno konfigurací.** Běží jen když `settings.seed_on_start` je pravda.
  Zapojeno do startu aplikace (`main.py` lifespan) až po inicializaci enginu;
  schéma je v tu chvíli hotové, protože migrace pouští entrypoint kontejneru
  před spuštěním serveru (design.md 6.4, 13).

**Vazba na demo účet v Dexu.** Právě jedna osoba má roli `ADMIN` a odpovídá
administrátorskému demo účtu v `deploy/dex/config.yaml`: e-mail
`spravce@regina.local`, jméno „Jana Nováková". `oidc_subject` se seedovaným
řádkům **nenastavuje** (zůstává prázdný) — doplní se až při prvním přihlášení
párováním podle e-mailu (`auth._match_person`, R11.7). Tím je zároveň ověřeno,
že osoba může být v adresáři dřív, než se poprvé přihlásí.

**Invariant klasifikace (database.md 4).** Denormalizovaný sloupec
`applications.classification` musí vždy odpovídat klasifikaci **posledního**
řádku v `classification_log` dané aplikace (nejnovější podle `created_at`).
Seed to garantuje tím, že u aplikace s historií nejdřív vloží všechny log
řádky s rostoucími časovými značkami a `classification` záznamu nastaví na
klasifikaci posledního z nich. Aplikace bez historie mají `classification`
buď rovnou platné hodnotě zapsané „mimo log" pro demo, nebo NULL
(neklasifikováno).

**Logování.** Loguje se jen souhrn (počty), žádné jméno ani e-mail (R12.10).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from regina.config import Settings
from regina.db.models.applications import Application
from regina.db.models.classification_log import ClassificationLog
from regina.db.models.users import User
from regina.db.session import session_scope
from regina.domain.enums import (
    Classification,
    ClassificationSource,
    LifecycleState,
    Role,
    RoleSource,
)
from regina.logging import get_logger

logger = get_logger("regina.seed")

# E-mail administrátorského demo účtu v Dexu. MUSÍ se shodovat s
# `deploy/dex/config.yaml`, aby se první přihlášení přes Dex spárovalo s tímto
# řádkem podle e-mailu a doplnilo `oidc_subject` (design.md 4.2 krok 6, R11.7).
ADMIN_EMAIL = "spravce@regina.local"
ADMIN_DISPLAY_NAME = "Jana Nováková"


@dataclass(frozen=True)
class SeedPerson:
    """Předpis jedné seedované osoby.

    `email` je stabilní klíč: slouží k idempotenci (skip při existující osobě)
    i k dohledání osoby úkolem 9.2 při skládání odpovědné trojice u aplikací.
    """

    email: str
    display_name: str
    job_title: str
    role: Role = Role.USER


# Přibližně dvacet vymyšlených osob s českými jmény a pozicemi napříč útvary
# (design.md 14). Právě jedna má roli ADMIN a odpovídá demo účtu v Dexu; ostatní
# jsou USER. E-maily jsou v neexistující doméně `@regina.local`, takže jsou
# prokazatelně syntetické.
#
# Petr Svoboda (uzivatel@regina.local) odpovídá uživatelskému demo účtu v Dexu,
# aby i běžný uživatel měl po přihlášení spárovaný řádek v adresáři.
SEED_PEOPLE: tuple[SeedPerson, ...] = (
    SeedPerson(ADMIN_EMAIL, ADMIN_DISPLAY_NAME, "Vedoucí správy registru", Role.ADMIN),
    SeedPerson("uzivatel@regina.local", "Petr Svoboda", "Softwarový inženýr"),
    SeedPerson("marie.dvorakova@regina.local", "Marie Dvořáková", "Produktová manažerka"),
    SeedPerson("jan.novak@regina.local", "Jan Novák", "Vedoucí vývoje"),
    SeedPerson("eva.prochazkova@regina.local", "Eva Procházková", "Datová analytička"),
    SeedPerson("tomas.kucera@regina.local", "Tomáš Kučera", "DevOps inženýr"),
    SeedPerson("lucie.vesela@regina.local", "Lucie Veselá", "Scrum master"),
    SeedPerson("martin.horak@regina.local", "Martin Horák", "Solution architekt"),
    SeedPerson("katerina.nemcova@regina.local", "Kateřina Němcová", "Business analytička"),
    SeedPerson("pavel.marek@regina.local", "Pavel Marek", "Databázový specialista"),
    SeedPerson("jana.pospisilova@regina.local", "Jana Pospíšilová", "Manažerka rizik"),
    SeedPerson("ondrej.cerny@regina.local", "Ondřej Černý", "Bezpečnostní inženýr"),
    SeedPerson("tereza.kralova@regina.local", "Tereza Králová", "QA inženýrka"),
    SeedPerson("david.benes@regina.local", "David Beneš", "Frontend vývojář"),
    SeedPerson("veronika.fialova@regina.local", "Veronika Fialová", "UX designérka"),
    SeedPerson("filip.sedlacek@regina.local", "Filip Sedláček", "Backend vývojář"),
    SeedPerson("hana.ruzickova@regina.local", "Hana Růžičková", "Vedoucí HR systémů"),
    SeedPerson("petra.dolezalova@regina.local", "Petra Doležalová", "Finanční controllerka"),
    SeedPerson("michal.kolar@regina.local", "Michal Kolář", "Vedoucí IT provozu"),
    SeedPerson("simona.jandova@regina.local", "Simona Jandová", "Marketingová specialistka"),
    SeedPerson("radek.stastny@regina.local", "Radek Šťastný", "Integrace a API"),
)


def _existing_emails_lower(session: Session) -> set[str]:
    """Vrátí množinu e-mailů (malými písmeny) osob, které už v adresáři jsou.

    Jeden dotaz místo dotazu na osobu; idempotence se pak rozhoduje v paměti,
    shodně s `lower(email)` unikátním indexem.
    """
    rows = session.execute(select(func.lower(User.email))).scalars().all()
    return set(rows)


def seed_people(session: Session) -> int:
    """Vloží chybějící seedované osoby. Vrací počet nově vložených.

    Idempotentní: osoby, jejichž e-mail (bez ohledu na velikost písmen) už
    v adresáři je, se přeskočí a ponechají beze změny. Bezpečné volat při
    každém startu.

    `oidc_subject` se **nenastavuje** — doplní se při prvním přihlášení
    párováním podle e-mailu (R11.7).
    """
    existing = _existing_emails_lower(session)
    inserted = 0

    for person in SEED_PEOPLE:
        if person.email.lower() in existing:
            continue
        session.add(
            User(
                oidc_subject=None,
                email=person.email,
                display_name=person.display_name,
                job_title=person.job_title,
                role=person.role,
                role_source=RoleSource.LOCAL,
                is_active=True,
            )
        )
        # Průběžně evidujeme i nově přidané, aby duplicita v samotném seznamu
        # (nemělo by nastat) neskončila dvojím vložením v jednom běhu.
        existing.add(person.email.lower())
        inserted += 1

    return inserted


# --- Aplikace a historie klasifikace (úkol 9.2) -----------------------------
#
# Odpovědná trojice a aktéři v logu odkazují na osoby přes e-mail; při seedu se
# e-maily přeloží na `users.id` (viz `_email_to_user_id`). Admin
# (`spravce@regina.local`) je záměrně členem jen *některých* trojic — u těch
# může v UI editovat, u ostatních ne, takže demo ukáže oba případy oprávnění.

# Pevný základ času pro deterministické, ale realisticky vypadající značky
# v historii klasifikace. Konkrétní datum nehraje roli; důležité je jen pořadí
# uvnitř historie jedné aplikace (nejnovější řádek = platná klasifikace).
_LOG_EPOCH = datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SeedLogEntry:
    """Jeden řádek historie klasifikace pro seedovanou aplikaci.

    `actor_email` musí být osoba ze `SEED_PEOPLE`. U `HUMAN` to má být člen
    odpovědné trojice, u `ADMIN_OVERRIDE` administrátor. `reason` je povinný a
    neprázdný právě u `ADMIN_OVERRIDE` (database.md 5, `CHECK` constraint).
    `previous_classification` dává smysl u přepisu (hodnota před změnou).
    `order` určuje pořadí v čase — vyšší číslo je novější řádek.
    """

    order: int
    classification: Classification
    source: ClassificationSource
    actor_email: str
    previous_classification: Classification | None = None
    reason: str | None = None


@dataclass(frozen=True)
class SeedApplication:
    """Předpis jedné seedované aplikace.

    Idempotentní klíč je `name` bez ohledu na velikost písmen, shodně s
    `uq_applications_lower_name`. `classification` je **platná** hodnota na
    záznamu; pokud má aplikace historii (`log`), MUSÍ se rovnat klasifikaci
    posledního (nejnovějšího) řádku historie — to hlídá `_validate_seed_application`.
    Vyřazená aplikace (`DECOMMISSIONED`) MUSÍ mít `decommissioned_by`
    (kdo vyřadil); `decommissioned_at` doplní seed automaticky. Jiný stav ho
    mít nesmí (database.md 4, `CHECK` constraint).
    """

    name: str
    department: str
    lifecycle_state: LifecycleState
    owner_email: str
    tech_admin_email: str
    description: str
    deputy_email: str | None = None
    ai_model: str | None = None
    classification: Classification | None = None
    decommissioned_by_email: str | None = None
    log: tuple[SeedLogEntry, ...] = field(default_factory=tuple)


# Zkratky e-mailů kvůli čitelnosti tabulky níže.
_ADMIN = ADMIN_EMAIL
_USER = "uzivatel@regina.local"
_MARIE = "marie.dvorakova@regina.local"
_JAN = "jan.novak@regina.local"
_EVA = "eva.prochazkova@regina.local"
_TOMAS = "tomas.kucera@regina.local"
_LUCIE = "lucie.vesela@regina.local"
_MARTIN = "martin.horak@regina.local"
_KATERINA = "katerina.nemcova@regina.local"
_PAVEL = "pavel.marek@regina.local"
_JANA_P = "jana.pospisilova@regina.local"
_ONDREJ = "ondrej.cerny@regina.local"
_TEREZA = "tereza.kralova@regina.local"
_DAVID = "david.benes@regina.local"
_VERONIKA = "veronika.fialova@regina.local"
_FILIP = "filip.sedlacek@regina.local"
_HANA = "hana.ruzickova@regina.local"
_PETRA = "petra.dolezalova@regina.local"
_MICHAL = "michal.kolar@regina.local"
_SIMONA = "simona.jandova@regina.local"
_RADEK = "radek.stastny@regina.local"

# Zkratky výčtů.
_DRAFT = LifecycleState.DRAFT
_DEV = LifecycleState.IN_DEVELOPMENT
_TEST = LifecycleState.TESTING
_PROD = LifecycleState.IN_PRODUCTION
_DECOM = LifecycleState.DECOMMISSIONED
_S = Classification.SMALL
_M = Classification.MEDIUM
_L = Classification.LARGE
_HUMAN = ClassificationSource.HUMAN
_OVERRIDE = ClassificationSource.ADMIN_OVERRIDE


# Přibližně třicet vymyšlených aplikací napříč všemi útvary
# (Finance, HR, IT Ops, Risk, Marketing, Provoz), všemi stavy životního cyklu
# a klasifikacemi MALÁ/STŘEDNÍ/VELKÁ. Několik záznamů je záměrně
# **neklasifikovaných** (classification=None) a několik **vyřazených**
# (DECOMMISSIONED s vyplněným `decommissioned_by`). U části je vyplněná historie
# klasifikace, včetně přepisu správcem s českým důvodem.
#
# Admin (`spravce@regina.local`) je členem trojice jen u některých aplikací —
# viz vlastník/zástupce/správce níže — takže demo ukáže „můžu editovat" i
# „nemůžu editovat".
SEED_APPLICATIONS: tuple[SeedApplication, ...] = (
    # --- Finance ---
    SeedApplication(
        name="Fakturační portál",
        department="Finance",
        lifecycle_state=_PROD,
        owner_email=_PETRA,
        deputy_email=_MARIE,
        tech_admin_email=_PAVEL,
        description="Interní portál pro vystavování a schvalování faktur dodavatelům.",
        ai_model="GPT-4o",
        classification=_L,
        log=(
            SeedLogEntry(1, _M, _HUMAN, _PETRA),
            SeedLogEntry(
                2,
                _L,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_M,
                reason="Portál zpracovává platební údaje napříč celou firmou, "
                "riziko odpovídá velké aplikaci.",
            ),
        ),
    ),
    SeedApplication(
        name="Nástroj pro rozpočtové plánování",
        department="Finance",
        lifecycle_state=_DEV,
        owner_email=_MARIE,
        tech_admin_email=_FILIP,
        description="Sestavování a sledování ročních rozpočtů jednotlivých útvarů.",
        classification=_M,
        log=(SeedLogEntry(1, _M, _HUMAN, _MARIE),),
    ),
    SeedApplication(
        name="Evidence pohledávek",
        department="Finance",
        lifecycle_state=_TEST,
        owner_email=_PETRA,
        deputy_email=_KATERINA,
        tech_admin_email=_PAVEL,
        description="Přehled otevřených pohledávek a upomínkový proces.",
        ai_model="Claude 3.5",
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Kalkulačka DPH",
        department="Finance",
        lifecycle_state=_DRAFT,
        owner_email=_MARIE,
        tech_admin_email=_PAVEL,
        description="Pomůcka pro výpočet a kontrolu DPH u přeshraničních plnění.",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _MARIE),),
    ),
    SeedApplication(
        name="Archiv daňových přiznání",
        department="Finance",
        lifecycle_state=_DECOM,
        owner_email=_PETRA,
        tech_admin_email=_PAVEL,
        description="Původní archiv daňových přiznání nahrazený novým DMS.",
        classification=_S,
        decommissioned_by_email=_ADMIN,
        log=(SeedLogEntry(1, _S, _HUMAN, _PETRA),),
    ),
    # --- HR ---
    SeedApplication(
        name="Nástupní průvodce zaměstnance",
        department="HR",
        lifecycle_state=_PROD,
        owner_email=_HANA,
        deputy_email=_LUCIE,
        tech_admin_email=_DAVID,
        description="Provede nového kolegu prvními dny a nastaví přístupy.",
        ai_model="GPT-4o mini",
        classification=_M,
        log=(
            SeedLogEntry(1, _S, _HUMAN, _HANA),
            SeedLogEntry(2, _M, _HUMAN, _LUCIE),
        ),
    ),
    SeedApplication(
        name="Docházkový systém",
        department="HR",
        lifecycle_state=_PROD,
        owner_email=_HANA,
        tech_admin_email=_MICHAL,
        description="Evidence pracovní doby, dovolených a home office.",
        classification=_L,
        log=(
            SeedLogEntry(1, _M, _HUMAN, _HANA),
            SeedLogEntry(
                2,
                _L,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_M,
                reason="Systém eviduje osobní údaje všech zaměstnanců, "
                "patří mezi velké aplikace.",
            ),
        ),
    ),
    SeedApplication(
        name="Portál zaměstnaneckých benefitů",
        department="HR",
        lifecycle_state=_DEV,
        owner_email=_HANA,
        deputy_email=_SIMONA,
        tech_admin_email=_DAVID,
        description="Výběr a čerpání benefitů z ročního bodového rozpočtu.",
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Hodnocení výkonu",
        department="HR",
        lifecycle_state=_TEST,
        owner_email=_LUCIE,
        deputy_email=_TEREZA,
        tech_admin_email=_DAVID,
        description="Podpora pravidelných hodnoticích pohovorů a cílů.",
        ai_model="Claude 3.5",
        classification=_M,
        log=(SeedLogEntry(1, _M, _HUMAN, _LUCIE),),
    ),
    SeedApplication(
        name="Interní kariérní burza",
        department="HR",
        lifecycle_state=_DECOM,
        owner_email=_HANA,
        tech_admin_email=_DAVID,
        description="Nabídka interních pozic, nahrazena modulem v HR systému.",
        classification=_M,
        decommissioned_by_email=_ADMIN,
        log=(
            SeedLogEntry(1, _S, _HUMAN, _HANA),
            SeedLogEntry(2, _M, _HUMAN, _HANA),
        ),
    ),
    # --- IT Ops ---
    SeedApplication(
        name="Registr interních aplikací",
        department="IT Ops",
        lifecycle_state=_PROD,
        owner_email=_ADMIN,
        deputy_email=_JAN,
        tech_admin_email=_TOMAS,
        description="Tato evidence interních aplikací a jejich klasifikace.",
        ai_model="GPT-4o",
        classification=_L,
        log=(
            SeedLogEntry(1, _M, _HUMAN, _JAN),
            SeedLogEntry(
                2,
                _L,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_M,
                reason="Registr je zdroj pravdy o klasifikaci všech aplikací, "
                "jeho výpadek má firemní dopad.",
            ),
        ),
    ),
    SeedApplication(
        name="Monitoring infrastruktury",
        department="IT Ops",
        lifecycle_state=_PROD,
        owner_email=_MICHAL,
        deputy_email=_MARTIN,
        tech_admin_email=_TOMAS,
        description="Sběr metrik a upozornění na výpadky serverů a služeb.",
        classification=_L,
        log=(SeedLogEntry(1, _L, _HUMAN, _MICHAL),),
    ),
    SeedApplication(
        name="Správce přístupových práv",
        department="IT Ops",
        lifecycle_state=_DEV,
        owner_email=_ONDREJ,
        tech_admin_email=_TOMAS,
        description="Žádosti o přístupy a jejich schvalovací proces.",
        ai_model=None,
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Katalog IT služeb",
        department="IT Ops",
        lifecycle_state=_TEST,
        owner_email=_MICHAL,
        deputy_email=_USER,
        tech_admin_email=_TOMAS,
        description="Přehled poskytovaných IT služeb a jejich objednávání.",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _MICHAL),),
    ),
    SeedApplication(
        name="Nástroj pro nasazování",
        department="IT Ops",
        lifecycle_state=_DRAFT,
        owner_email=_TOMAS,
        tech_admin_email=_FILIP,
        description="Automatizace nasazení aplikací do prostředí.",
        classification=_M,
        log=(SeedLogEntry(1, _M, _HUMAN, _TOMAS),),
    ),
    SeedApplication(
        name="Starý ticketovací systém",
        department="IT Ops",
        lifecycle_state=_DECOM,
        owner_email=_MICHAL,
        tech_admin_email=_TOMAS,
        description="Původní helpdesk nahrazený novou service desk platformou.",
        classification=_M,
        decommissioned_by_email=_ADMIN,
    ),
    # --- Risk ---
    SeedApplication(
        name="Skórování úvěrového rizika",
        department="Risk",
        lifecycle_state=_PROD,
        owner_email=_JANA_P,
        deputy_email=_EVA,
        tech_admin_email=_PAVEL,
        description="Vyhodnocení bonity žadatele podle interního modelu.",
        ai_model="GPT-4o",
        classification=_L,
        log=(
            SeedLogEntry(1, _M, _HUMAN, _JANA_P),
            SeedLogEntry(
                2,
                _L,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_M,
                reason="Model přímo ovlivňuje rozhodování o úvěrech, "
                "vyžaduje nejpřísnější režim.",
            ),
        ),
    ),
    SeedApplication(
        name="Registr rizik",
        department="Risk",
        lifecycle_state=_PROD,
        owner_email=_JANA_P,
        tech_admin_email=_ONDREJ,
        description="Evidence identifikovaných rizik a opatření.",
        classification=_M,
        log=(SeedLogEntry(1, _M, _HUMAN, _JANA_P),),
    ),
    SeedApplication(
        name="Detekce podvodů",
        department="Risk",
        lifecycle_state=_DEV,
        owner_email=_EVA,
        deputy_email=_JANA_P,
        tech_admin_email=_PAVEL,
        description="Vyhledávání neobvyklých vzorů v transakcích.",
        ai_model="Claude 3.5",
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Reporting compliance",
        department="Risk",
        lifecycle_state=_TEST,
        owner_email=_JANA_P,
        tech_admin_email=_ONDREJ,
        description="Sestavy pro regulatorní hlášení a interní kontrolu.",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _JANA_P),),
    ),
    SeedApplication(
        name="Kalkulačka kapitálové přiměřenosti",
        department="Risk",
        lifecycle_state=_DECOM,
        owner_email=_JANA_P,
        tech_admin_email=_PAVEL,
        description="Výpočet nahrazený centrálním regulatorním nástrojem.",
        classification=_L,
        decommissioned_by_email=_ADMIN,
        log=(
            SeedLogEntry(1, _M, _HUMAN, _JANA_P),
            SeedLogEntry(
                2,
                _L,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_M,
                reason="Před vyřazením přeřazeno mezi velké kvůli dopadu "
                "na regulatorní výkazy.",
            ),
        ),
    ),
    # --- Marketing ---
    SeedApplication(
        name="Kampaňový plánovač",
        department="Marketing",
        lifecycle_state=_PROD,
        owner_email=_SIMONA,
        deputy_email=_VERONIKA,
        tech_admin_email=_DAVID,
        description="Plánování a vyhodnocování marketingových kampaní.",
        ai_model="GPT-4o",
        classification=_M,
        log=(
            SeedLogEntry(1, _S, _HUMAN, _SIMONA),
            SeedLogEntry(2, _M, _HUMAN, _SIMONA),
        ),
    ),
    SeedApplication(
        name="Generátor obsahu sociálních sítí",
        department="Marketing",
        lifecycle_state=_DEV,
        owner_email=_SIMONA,
        tech_admin_email=_DAVID,
        description="Návrhy příspěvků na sociální sítě podle zadaného tématu.",
        ai_model="Claude 3.5 Sonnet",
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Správa newsletterů",
        department="Marketing",
        lifecycle_state=_TEST,
        owner_email=_VERONIKA,
        tech_admin_email=_FILIP,
        description="Příprava a rozesílka e-mailových newsletterů.",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _VERONIKA),),
    ),
    SeedApplication(
        name="Přehled značky",
        department="Marketing",
        lifecycle_state=_DRAFT,
        owner_email=_SIMONA,
        deputy_email=_ADMIN,
        tech_admin_email=_DAVID,
        description="Sledování zmínek o značce a sentimentu.",
        ai_model="GPT-4o mini",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _SIMONA),),
    ),
    SeedApplication(
        name="Bannerový systém",
        department="Marketing",
        lifecycle_state=_DECOM,
        owner_email=_VERONIKA,
        tech_admin_email=_DAVID,
        description="Rotace reklamních bannerů na interních portálech, ukončeno.",
        classification=None,  # neklasifikováno a vyřazeno
        decommissioned_by_email=_ADMIN,
    ),
    # --- Provoz ---
    SeedApplication(
        name="Rezervace zasedacích místností",
        department="Provoz",
        lifecycle_state=_PROD,
        owner_email=_MICHAL,
        deputy_email=_LUCIE,
        tech_admin_email=_RADEK,
        description="Rezervace zasedacích místností a sdílených zdrojů.",
        classification=_S,
        log=(SeedLogEntry(1, _S, _HUMAN, _MICHAL),),
    ),
    SeedApplication(
        name="Evidence majetku",
        department="Provoz",
        lifecycle_state=_PROD,
        owner_email=_MICHAL,
        tech_admin_email=_RADEK,
        description="Evidence firemního majetku a jeho přiřazení.",
        classification=_M,
        log=(
            SeedLogEntry(1, _S, _HUMAN, _MICHAL),
            SeedLogEntry(
                2,
                _M,
                _OVERRIDE,
                _ADMIN,
                previous_classification=_S,
                reason="Rozsah evidovaného majetku a vazba na účetnictví "
                "odpovídá střední aplikaci.",
            ),
        ),
    ),
    SeedApplication(
        name="Kniha jízd",
        department="Provoz",
        lifecycle_state=_DEV,
        owner_email=_RADEK,
        tech_admin_email=_TOMAS,
        description="Evidence služebních jízd a spotřeby vozového parku.",
        classification=None,  # neklasifikováno
    ),
    SeedApplication(
        name="Správa dodavatelů",
        department="Provoz",
        lifecycle_state=_TEST,
        owner_email=_KATERINA,
        deputy_email=_MICHAL,
        tech_admin_email=_RADEK,
        description="Evidence dodavatelů, smluv a jejich platnosti.",
        ai_model="GPT-4o",
        classification=_M,
        log=(SeedLogEntry(1, _M, _HUMAN, _KATERINA),),
    ),
    SeedApplication(
        name="Recepční tablet",
        department="Provoz",
        lifecycle_state=_DECOM,
        owner_email=_MICHAL,
        tech_admin_email=_RADEK,
        description="Odbavení návštěv na recepci, nahrazeno novým řešením.",
        classification=_S,
        decommissioned_by_email=_ADMIN,
        log=(SeedLogEntry(1, _S, _HUMAN, _MICHAL),),
    ),
)


def _email_to_user_id(session: Session) -> dict[str, uuid.UUID]:
    """Sestaví mapu e-mail (malými písmeny) → `users.id` pro seedované osoby.

    Aplikace odkazují osoby přes e-mail; při zápisu se musí přeložit na cizí
    klíč. Jeden dotaz nad adresářem, klíč je `lower(email)` shodně s idempotencí
    osob.
    """
    rows = session.execute(select(func.lower(User.email), User.id)).all()
    return {email: user_id for email, user_id in rows}


def _existing_app_names_lower(session: Session) -> set[str]:
    """Množina názvů aplikací (malými písmeny), které už v registru jsou.

    Idempotence aplikací se rozhoduje shodně s `uq_applications_lower_name`.
    """
    rows = session.execute(select(func.lower(Application.name))).scalars().all()
    return set(rows)


def _validate_seed_application(spec: SeedApplication) -> None:
    """Ověří, že předpis aplikace ctí databázové constrainty ještě před zápisem.

    Chytí chybu v datové tabulce dřív, než ji odmítne databáze, a s jasnější
    zprávou. Kontroluje invariant klasifikace vůči historii, vazbu vyřazení a
    povinný důvod u přepisu správcem.
    """
    is_decommissioned = spec.lifecycle_state is _DECOM

    # decommissioned_at IFF DECOMMISSIONED (database.md 4). `decommissioned_at`
    # doplňuje seed automaticky, ale `decommissioned_by` musí být zadán právě
    # u vyřazených a jen u nich.
    if is_decommissioned and spec.decommissioned_by_email is None:
        raise ValueError(
            f"Aplikace {spec.name!r} je DECOMMISSIONED, ale nemá decommissioned_by."
        )
    if not is_decommissioned and spec.decommissioned_by_email is not None:
        raise ValueError(
            f"Aplikace {spec.name!r} není DECOMMISSIONED, přesto má decommissioned_by."
        )

    if spec.log:
        orders = [entry.order for entry in spec.log]
        if len(set(orders)) != len(orders):
            raise ValueError(f"Aplikace {spec.name!r} má v historii duplicitní pořadí.")
        # Invariant: platná klasifikace = klasifikace posledního (nejnovějšího)
        # řádku historie (database.md 4).
        last_entry = max(spec.log, key=lambda entry: entry.order)
        if spec.classification is not last_entry.classification:
            raise ValueError(
                f"Aplikace {spec.name!r}: classification "
                f"{spec.classification} != poslední řádek historie "
                f"{last_entry.classification}."
            )

    for entry in spec.log:
        # Povinný neprázdný důvod u ADMIN_OVERRIDE (database.md 5, CHECK).
        if entry.source is _OVERRIDE and not (entry.reason and entry.reason.strip()):
            raise ValueError(
                f"Aplikace {spec.name!r}: ADMIN_OVERRIDE bez neprázdného důvodu."
            )
        if entry.source is not _OVERRIDE and entry.reason is not None:
            raise ValueError(
                f"Aplikace {spec.name!r}: důvod smí mít jen ADMIN_OVERRIDE."
            )


def seed_applications(session: Session) -> tuple[int, int]:
    """Vloží chybějící seedované aplikace a jejich historii klasifikace.

    Vrací dvojici (počet nově vložených aplikací, počet nově vložených řádků
    historie). Idempotentní: aplikace, jejíž název (bez ohledu na velikost
    písmen) už v registru je, se přeskočí a **nepřidá se ani její historie** —
    log tak při opakovaném startu nenarůstá.

    Předpokládá, že osoby už jsou zavedené (`seed_people`), protože odpovědná
    trojice a aktéři v logu na ně odkazují cizím klíčem.

    Pořadí v transakci ctí invariant z database.md 4: pro aplikaci s historií
    se nejdřív vloží log řádky s rostoucími časovými značkami a `classification`
    záznamu se rovná klasifikaci nejnovějšího z nich.
    """
    people = _email_to_user_id(session)
    existing = _existing_app_names_lower(session)

    apps_inserted = 0
    logs_inserted = 0

    def resolve(email: str) -> uuid.UUID:
        user_id = people.get(email.lower())
        if user_id is None:
            raise ValueError(
                f"Seed aplikací odkazuje osobu {email!r}, která není v adresáři. "
                "Osoby se musí seedovat před aplikacemi."
            )
        return user_id

    for spec in SEED_APPLICATIONS:
        if spec.name.lower() in existing:
            continue

        _validate_seed_application(spec)

        decommissioned_at = None
        decommissioned_by = None
        if spec.lifecycle_state is _DECOM:
            assert spec.decommissioned_by_email is not None  # zajištěno validací
            decommissioned_by = resolve(spec.decommissioned_by_email)
            # Konkrétní okamžik nehraje roli, jen musí být vyplněný (CHECK).
            decommissioned_at = _LOG_EPOCH + timedelta(days=200)

        application = Application(
            name=spec.name,
            description=spec.description,
            department=spec.department,
            lifecycle_state=str(spec.lifecycle_state),
            owner_user_id=resolve(spec.owner_email),
            deputy_user_id=resolve(spec.deputy_email) if spec.deputy_email else None,
            tech_admin_user_id=resolve(spec.tech_admin_email),
            ai_model=spec.ai_model,
            classification=str(spec.classification) if spec.classification else None,
            decommissioned_at=decommissioned_at,
            decommissioned_by=decommissioned_by,
            created_by_user_id=resolve(spec.owner_email),
        )
        session.add(application)
        # Potřebujeme `application.id` pro cizí klíč v log řádcích.
        session.flush()
        apps_inserted += 1
        existing.add(spec.name.lower())

        # Historie se vkládá v pořadí `order`, s rostoucím `created_at`, aby
        # nejnovější řádek (a tím i platná klasifikace) byl jednoznačný.
        for entry in sorted(spec.log, key=lambda item: item.order):
            session.add(
                ClassificationLog(
                    application_id=application.id,
                    classification=str(entry.classification),
                    previous_classification=(
                        str(entry.previous_classification)
                        if entry.previous_classification
                        else None
                    ),
                    source=str(entry.source),
                    reason=entry.reason,
                    actor_user_id=resolve(entry.actor_email),
                    created_at=_LOG_EPOCH + timedelta(hours=entry.order),
                )
            )
            logs_inserted += 1

    return apps_inserted, logs_inserted


def run_seed(settings: Settings) -> None:
    """Spustí naplnění syntetickými daty, pokud je zapnuté konfigurací.

    Řízeno `settings.seed_on_start` (R12.9). Otevírá vlastní transakci přes
    `session_scope`, takže se dá volat přímo ze startu aplikace nezávisle na
    obsluze požadavku. Loguje jen souhrnné počty, žádnou osobní hodnotu (R12.10).
    """
    if not settings.seed_on_start:
        logger.info(
            "Naplnění syntetickými daty přeskočeno (SEED_ON_START vypnuto)",
            extra={"event": "seed.skipped"},
        )
        return

    with session_scope() as session:
        # Osoby první — aplikace na ně odkazují odpovědnou trojicí i aktéry
        # v historii klasifikace. Vše v jedné transakci `session_scope`, takže
        # při chybě se nezapíše nic (aplikace bez zavedených osob nedávají smysl).
        inserted_people = seed_people(session)
        inserted_apps, inserted_logs = seed_applications(session)

        total_people = session.execute(select(func.count()).select_from(User)).scalar_one()
        total_apps = session.execute(
            select(func.count()).select_from(Application)
        ).scalar_one()
        total_logs = session.execute(
            select(func.count()).select_from(ClassificationLog)
        ).scalar_one()

    logger.info(
        "Naplnění syntetickými daty dokončeno",
        extra={
            "event": "seed.completed",
            "people_inserted": inserted_people,
            "people_total": total_people,
            "applications_inserted": inserted_apps,
            "applications_total": total_apps,
            "classification_log_inserted": inserted_logs,
            "classification_log_total": total_logs,
        },
    )
