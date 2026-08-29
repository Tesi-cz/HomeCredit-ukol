"""Zápis klasifikace (design.md 5.1, database.md 4 a 5, R6, R7).

Tohle je **jediné** místo v celé aplikaci, které smí měnit denormalizovaný
sloupec ``applications.classification``. Žádná jiná cesta ho nesmí nastavit
napřímo — vytvoření záznamu, editace i přepis správcem procházejí touto funkcí
(design.md 5.1). Udržet to na jednom místě je celý smysl denormalizace: sloupec
na ``applications`` nese platnou hodnotu kvůli výpisu (filtr, řazení, badge),
zatímco historii drží ``classification_log``. Cenou je invariant, který drží
aplikace, ne databáze:

    *Zápis do ``classification_log`` a aktualizace ``applications.classification``
    probíhá v jedné transakci. Po zápisu se sloupec rovná klasifikaci
    posledního (nejnovějšího) řádku logu.* (database.md 4, R6.2)

Funkce ho drží pořadím operací v jedné transakci volajícího: (1) zjistí
předchozí hodnotu ze sloupce, (2) přidá řádek do ``classification_log`` s touto
předchozí hodnotou i novou hodnotou, (3) nastaví sloupec na novou hodnotu, (4)
zapíše auditní záznam. Vše ve **stejné** session — funkce sama **necommituje**
(design.md 6.3); o transakci se stará vrstva, která ji volá. Log řádek i změna
sloupce se tak potvrdí atomicky a sloupec nikdy nemůže odpovídat jinému než
poslednímu řádku logu.

**Audit podle zdroje.** Zápis člověkem (``HUMAN``) píše ``CLASSIFICATION_SET``
(R6.9), přepis správcem (``ADMIN_OVERRIDE``) píše ``CLASSIFICATION_OVERRIDDEN``
(R7.7) — přes obálky ve ``services/audit.py``, ve stejné transakci jako změna.

**Rozšiřitelnost pro poradce.** Podpis se navazující specifikací
``classification-advisor`` nemění (design.md 15): přidá se jen nepovinný odkaz
na doporučení a zdroje ``AI`` / ``AI_OVERRIDDEN``. Proto se tu nikde
nepředpokládá, že jsou zdroje právě dva; auditní akce se odvozuje výslovně od
``ADMIN_OVERRIDE`` a ostatní zdroje se chovají jako „člověk zapsal".

**Rozsah úkolu 13.1.** Jádro jednoho zapisovače + transakční invariant + audit.
Rychlá pojistka: ``ADMIN_OVERRIDE`` s prázdným nebo jen bílým důvodem nelze
zapsat (jinak by ho stejně odmítl ``CHECK`` constraint ``admin_override_requires_reason``,
tady ale selže dřív a s jasnější zprávou).

**Rozsah úkolu 13.2 — politika přepisu nad jádrem.** ``write_classification``
zůstává neutrálním jediným zapisovačem. Nad ním stojí dva vstupní body, které
volají služby a routy:

- ``set_classification`` — běžný zápis členem odpovědné trojice se
  ``source = HUMAN``; **nevyžaduje** důvod (R6.3);
- ``override_classification`` — přepis správcem se ``source = ADMIN_OVERRIDE``.
  Sám ověří oprávnění přes ``domain.rules.can_override_classification`` a
  vyhradí operaci roli Admin (R7.1, R7.6). Běžnému uživateli ji odmítne
  vlastní výjimkou ``ClassificationPermissionError`` — **nezávisle** na HTTP
  guardu (obrana do hloubky). Důvod je povinný a neprázdný; prázdný odmítne
  přes rychlou pojistku z ``write_classification`` (R7.2, R7.3).

**Volba typu chyby pro neoprávněný přepis.** Služba vyhazuje **service-level**
výjimku ``ClassificationPermissionError``, ne ``AuthorizationError`` z
``auth/deps``. Důvod je vrstvení: ``services`` nesmí záviset na ``auth``/HTTP
(design.md sekce 1, závislosti míří dovnitř). HTTP routa (úkol 15) autorizaci
vynutí guardem ``require_override_classification`` a k routě se tak service-level
výjimka běžně vůbec nedostane; existuje jako obrana do hloubky pro volání mimo
HTTP (testy, budoucí interní volání). Vazba na ``auth`` by tuhle nezávislost
porušila.
"""

from __future__ import annotations

# Session se importuje jen pro typovou anotaci; funkce transakci nevytváří.
from sqlalchemy.orm import Session

from regina.db.models.applications import Application
from regina.db.models.classification_log import ClassificationLog
from regina.domain import rules
from regina.domain.enums import Classification, ClassificationSource
from regina.services import audit
from regina.services.audit import AuditActor


class ClassificationPermissionError(Exception):
    """Aktér nemá právo přepsat klasifikaci cizího záznamu (R7.1, R7.6).

    Service-level výjimka — **záměrně** není ``AuthorizationError`` z
    ``auth/deps``. Vrstva ``services`` nesmí záviset na ``auth`` ani na HTTP
    (design.md sekce 1). Vyhazuje ji ``override_classification``, když aktér
    není Admin, aby politika „přepis je jen pro Admina" platila i mimo HTTP
    guard (obrana do hloubky). HTTP routa (úkol 15) navíc pokus zachytí dřív
    guardem ``require_override_classification`` a přeloží ho na 403 + audit
    ``ACCESS_DENIED``; tato výjimka je pojistka pro cesty mimo guard.
    """


def write_classification(
    session: Session,
    application: Application,
    new_classification: Classification,
    actor: AuditActor,
    source: ClassificationSource,
    reason: str | None = None,
) -> ClassificationLog:
    """Zapíše klasifikaci aplikace — jediné místo, které mění ``classification``.

    V jedné transakci volajícího (bez commitu, design.md 6.3):

    1. zjistí předchozí hodnotu z ``application.classification``;
    2. přidá řádek do ``classification_log`` (nová i předchozí hodnota, zdroj,
       důvod, aktér, čas z databáze);
    3. nastaví ``application.classification`` na novou hodnotu;
    4. zapíše auditní záznam odpovídající zdroji.

    Po návratu se ``application.classification`` rovná klasifikaci právě
    zapsaného (a tím nejnovějšího) řádku logu — to je invariant z database.md 4
    (R6.2). Vrací vytvořený řádek logu pro případné navázání v testech a ve
    volající službě.

    Parametry:
        session: probíhající transakce volajícího. Funkce do ní jen zapisuje,
            necommituje ani nerolluje.
        application: záznam, jehož klasifikace se mění (načtený v této session).
        new_classification: nová platná klasifikace.
        actor: osoba provádějící zápis (``id``, ``email``, ``name`` pro audit a
            ``actor_user_id`` v logu).
        source: zdroj zápisu — ``HUMAN`` běžný zápis, ``ADMIN_OVERRIDE`` přepis
            správcem (rozšiřitelné o zdroje poradce, database.md 9).
        reason: důvod. U ``ADMIN_OVERRIDE`` povinný a neprázdný; jinak se
            neukládá (drží se pravidlo „důvod smí mít jen přepis").

    Vyvolá:
        ValueError: u ``ADMIN_OVERRIDE`` s prázdným nebo jen bílým důvodem —
            rychlá pojistka před databázovým ``CHECK`` constraintem (R7.2).
    """
    is_override = source is ClassificationSource.ADMIN_OVERRIDE

    # Rychlá pojistka nad databázovým CHECK constraintem
    # `admin_override_requires_reason` (database.md 5, R7.2): přepis správcem
    # musí mít neprázdný důvod. Plnou politiku přepisu doplní úkol 13.2; tady
    # jen chráníme jádro, aby se nedal zapsat nesmyslný řádek.
    normalized_reason = reason.strip() if reason is not None else None
    if is_override and not normalized_reason:
        raise ValueError(
            "Přepis klasifikace správcem (ADMIN_OVERRIDE) vyžaduje neprázdný "
            "důvod (R7.2)."
        )

    # Důvod se ukládá jen u přepisu; u ostatních zdrojů zůstává prázdný, aby
    # sloupec nesl důvod jen tam, kde dává smysl (database.md 5).
    stored_reason = normalized_reason if is_override else None

    # 1) Předchozí hodnota je současný denormalizovaný sloupec — před změnou.
    previous_value = application.classification

    # 2) Řádek historie. `created_at` doplní databáze (server_default now()),
    # takže je novější než všechny dřívější řádky a stává se posledním.
    log_entry = ClassificationLog(
        application_id=application.id,
        classification=str(new_classification),
        previous_classification=(str(previous_value) if previous_value else None),
        source=str(source),
        reason=stored_reason,
        actor_user_id=actor.id,
    )
    session.add(log_entry)

    # 3) Denormalizovaný sloupec = nově zapsaná hodnota. Po tomto řádku sloupec
    # odpovídá právě přidanému (nejnovějšímu) řádku logu — invariant drží.
    application.classification = str(new_classification)

    # 4) Audit ve stejné transakci (design.md 5.2): akce se odvíjí od zdroje.
    # ADMIN_OVERRIDE → CLASSIFICATION_OVERRIDDEN (R7.7); jakýkoli jiný zdroj
    # (dnes HUMAN, výhledově zdroje poradce) → CLASSIFICATION_SET (R6.9).
    if is_override:
        audit.classification_overridden(
            session,
            actor,
            entity_id=application.id,
            summary=f"Přepis klasifikace na {new_classification}.",
        )
    else:
        audit.classification_set(
            session,
            actor,
            entity_id=application.id,
            summary=f"Zápis klasifikace {new_classification}.",
        )

    return log_entry


def set_classification(
    session: Session,
    application: Application,
    actor: AuditActor,
    new_classification: Classification,
) -> ClassificationLog:
    """Běžný zápis klasifikace členem odpovědné trojice (R6.1, R6.3).

    Tenký vstupní bod pro vlastníky a členy trojice: zapisuje se ``source =
    HUMAN`` a **žádný důvod** — ten je vyhrazený jen přepisu správcem (R6.3,
    database.md 5). Oprávnění „člen trojice, nebo Admin" vynucuje HTTP guard
    ``require_can_set_classification`` (R6); zápis *cizího* záznamu je
    samostatná schopnost — viz ``override_classification`` (R7).

    Pod kapotou volá jediného zapisovače ``write_classification``, takže drží
    transakční invariant i auditní zápis (``CLASSIFICATION_SET``). Vrací
    vytvořený řádek logu.
    """
    return write_classification(
        session,
        application,
        new_classification,
        actor,
        ClassificationSource.HUMAN,
    )


def override_classification(
    session: Session,
    application: Application,
    actor: AuditActor,
    new_classification: Classification,
    reason: str,
) -> ClassificationLog:
    """Přepis klasifikace správcem — vyhrazeno roli Admin, s povinným důvodem.

    Politika přepisu (úkol 13.2, R7) vrstvená nad jediným zapisovačem:

    1. **Oprávnění (R7.1, R7.6).** Ověří ``rules.can_override_classification``
       (jen Admin). Když aktér Adminem není, vyhodí
       ``ClassificationPermissionError`` — tedy služba přepis odmítne sama,
       nezávisle na HTTP guardu (obrana do hloubky). Nic nezapíše.
    2. **Povinný důvod (R7.2, R7.3).** Zápis se zdrojem ``ADMIN_OVERRIDE`` a
       důvodem projde ``write_classification``, které prázdný nebo jen bílý
       důvod odmítne ``ValueError`` (rychlá pojistka nad databázovým ``CHECK``).
    3. **Log a audit (R7.4, R7.5, R7.7).** ``write_classification`` v jedné
       transakci vloží řádek do ``classification_log`` s předchozí hodnotou,
       novou hodnotou, důvodem a aktérem a zapíše audit
       ``CLASSIFICATION_OVERRIDDEN``.

    Podpis přijímá ``reason`` jako **povinný** parametr — přepis bez důvodu
    nemá dávat smysl už na úrovni volání. Prázdný řetězec přesto propadne do
    fail-fast kontroly v ``write_classification`` (R7.3).

    Parametry:
        session: probíhající transakce volajícího (bez commitu).
        application: cílový záznam (klidně cizí — přepis je definičně zásah do
            záznamu, kde Admin není členem trojice).
        actor: přihlášená osoba. Musí splňovat ``rules.Actor`` (``id``,
            ``role``) i ``AuditActor`` (``id``, ``email``, ``name``) —
            ``CurrentUser`` z ``auth/deps`` splňuje obojí.
        new_classification: nová platná klasifikace.
        reason: povinný neprázdný důvod přepisu.

    Vyvolá:
        ClassificationPermissionError: aktér není Admin (R7.1, R7.6).
        ValueError: prázdný nebo jen bílý důvod (R7.2, R7.3).
    """
    # 1) Obrana do hloubky (R7.1, R7.6): služba přepis odmítne sama, i kdyby ji
    # někdo zavolal mimo HTTP guard. Rozhoduje totéž čisté pravidlo, které volá
    # i guard `require_override_classification` (design.md 4.3).
    if not rules.can_override_classification(actor):
        raise ClassificationPermissionError(
            "Přepis klasifikace je vyhrazen roli Admin (R7.1, R7.6)."
        )

    # 2)–3) Povinný důvod, log a audit řeší jediný zapisovač se zdrojem
    # ADMIN_OVERRIDE. Prázdný důvod tam padne fail-fast (R7.2, R7.3).
    return write_classification(
        session,
        application,
        new_classification,
        actor,
        ClassificationSource.ADMIN_OVERRIDE,
        reason=reason,
    )
