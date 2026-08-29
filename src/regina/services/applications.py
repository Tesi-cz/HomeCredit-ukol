"""Vytvoření a editace záznamu aplikace (úkol 14.2, design.md 5, R5, R6).

Služba nad ověřeným formulářem (``web/forms.py``, úkol 14.1). Formulář sem
přichází už s ověřeným tvarem, výčty i kolizemi (název, existence osob) — tato
vrstva už **nevaliduje**, jen skládá a mění ORM záznam, zapisuje audit a
klasifikaci nechává projít jediným zapisovačem.

Běží v transakci volajícího (routa, design.md 6.3): funkce jen zapisují do
předané session, **necommitují** ani nerollují. Audit vzniká ve stejné
transakci jako změna (design.md 5.2), takže nemůže být změna bez auditu.

**Klasifikace nikdy napřímo.** ``applications.classification`` se v celé
aplikaci mění výhradně přes ``services.classification.write_classification``
(design.md 5.1, R6.1). Tato služba proto sloupec **nikdy nenastaví přiřazením**
— počáteční i změněnou klasifikaci směruje přes ``set_classification`` se
``source = HUMAN``. Tím drží transakční invariant „sloupec = poslední řádek
``classification_log``" a zapíše se audit ``CLASSIFICATION_SET`` (R6.2, R6.9).

**Audit editace nese jen názvy polí.** ``update_application`` spočítá, která
nesouvisející pole se opravdu změnila (porovnáním formuláře proti aktuální
hodnotě záznamu), a předá do auditu **jen jejich názvy**, nikdy hodnoty (R5.9,
R8.6, R12.10). Jméno pole je klíč formuláře z ``forms.FIELD_*``, aby audit,
formulář i šablona mluvily týmž jazykem. Zápis vynucuje i sám ``audit.record``,
který mapu hodnot odmítne ``TypeError``.

**Rozhodnutí: klasifikace jako součást editačního formuláře.** R5.6 říká, že
klasifikaci lze nastavit přímo na formuláři záznamu, a průvodce (úkol 14.3) ji
v kroku 3 sbírá. Obě funkce proto klasifikaci z formuláře přijímají a směrují
ji přes ``set_classification`` (``source = HUMAN``), **ne** přiřazením sloupce.
``classification`` se přitom **nezapočítává** do ``changed_fields`` editace:
její změnu plně zaznamenává ``classification_log`` (předchozí i nová hodnota) a
vlastní audit ``CLASSIFICATION_SET``; duplikovat ji ještě názvem pole v
``APP_UPDATED`` by bylo matoucí. Přepis *cizího* záznamu správcem
(``ADMIN_OVERRIDE``, R7) sem nepatří — má vlastní akci (úkol 15) přes
``override_classification``.

**Rozhodnutí: stav životního cyklu a vyřazení.** Constraint
``decommissioned_at_iff_decommissioned`` (database.md 4) vyžaduje, aby
``decommissioned_at`` bylo vyplněné právě tehdy, když je stav
``DECOMMISSIONED``. Přechod do/z ``DECOMMISSIONED`` doplňuje/čistí
``decommissioned_at`` a ``decommissioned_by`` a je vyhrazen roli Admin — to je
**samostatná akce** (úkol 15.2), ne běžná editace. Aby běžná editace nemohla
constraint porušit, obě funkce **odmítnou** nastavit ``lifecycle_state`` na
``DECOMMISSIONED`` (a ``create`` odmítne i vznik rovnou vyřazeného záznamu):
vyhodí ``LifecycleTransitionError``. Návrat ze stavu ``DECOMMISSIONED`` běžnou
editací je z téhož důvodu blokován — čištění ``decommissioned_at`` řeší
dedikovaná akce. Ostatní přechody (DRAFT → IN_PRODUCTION apod.) běžná editace
zvládá bez dopadu na constraint.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from regina.db.models.applications import Application
from regina.domain.enums import LifecycleState
from regina.services import audit
from regina.services.audit import AuditActor
from regina.services.classification import set_classification
from regina.web import forms
from regina.web.forms import ApplicationForm

#: Nesouvisející (ne-klasifikační) pole, která smí měnit běžná editace, a jejich
#: čtení z ověřeného formuláře. Klíč = název pole (``forms.FIELD_*``), který se
#: použije i v ``changed_fields`` auditu. ``classification`` zde **není** —
#: prochází výhradně ``write_classification`` a má vlastní audit i log.
#: ``lifecycle_state`` zde **je** (běžné přechody), ale přechod do/z
#: ``DECOMMISSIONED`` blokuje ``_reject_decommission_via_edit`` níž.
_EDITABLE_FIELDS: tuple[str, ...] = (
    forms.FIELD_NAME,
    forms.FIELD_DESCRIPTION,
    forms.FIELD_DEPARTMENT,
    forms.FIELD_OWNER,
    forms.FIELD_DEPUTY,
    forms.FIELD_TECH_ADMIN,
    forms.FIELD_LIFECYCLE_STATE,
    forms.FIELD_AI_MODEL,
)


class LifecycleTransitionError(Exception):
    """Vyřazení nelze provést běžnou editací (R5.12, database.md 4).

    Přechod do/z stavu ``DECOMMISSIONED`` doplňuje/čistí ``decommissioned_at``
    a ``decommissioned_by``, je vyhrazen roli Admin a má vlastní akci (úkol
    15.2). Běžná editace by porušila constraint
    ``decommissioned_at_iff_decommissioned``, proto ji služba odmítne dřív, než
    k databázi vůbec dojde.
    """


def _form_value(form: ApplicationForm, field: str) -> object:
    """Hodnota pole z formuláře jako čitelný atribut záznamu.

    Výčet ``lifecycle_state`` je ``StrEnum`` — do sloupce ``text`` se ukládá
    jako jeho strojový kód (``str``), aby odpovídal ``CHECK`` constraintu a
    porovnání proti hodnotě ze sloupce fungovalo. UUID a text se přebírají
    beze změny; prázdná nepovinná pole už formulář převedl na ``None``.
    """
    value = getattr(form, field)
    if isinstance(value, LifecycleState):
        return str(value)
    return value


def _reject_decommission_via_edit(form: ApplicationForm) -> None:
    """Odmítne pokus nastavit stav ``DECOMMISSIONED`` běžnou cestou.

    Vyřazení a návrat jsou dedikovaná akce (úkol 15.2) kvůli
    ``decommissioned_at``/``decommissioned_by`` a roli Admin. Běžná editace i
    vznik záznamu proto stav ``DECOMMISSIONED`` nepovolí (constraint-safety).
    """
    if form.lifecycle_state is LifecycleState.DECOMMISSIONED:
        raise LifecycleTransitionError(
            "Vyřazení záznamu se neprovádí přes formulář — použij akci vyřazení "
            "(vyhrazenou roli Admin)."
        )


def create_application(
    session: Session,
    actor: AuditActor,
    form: ApplicationForm,
) -> Application:
    """Založí nový záznam z ověřeného formuláře; zapíše audit a klasifikaci.

    Postup v transakci volajícího (bez commitu, design.md 6.3):

    1. Poskládá ``Application`` z nesouvisejících (ne-klasifikačních) polí
       formuláře a nastaví ``created_by_user_id = actor.id``. Vlastník je v
       ``form.owner_user_id`` — routa ho předvyplňuje tvůrcem, ale formulář
       dovolil změnu před uložením (R5.5), takže se sem přebírá tak, jak přišel.
    2. ``session.add`` + ``session.flush`` — flush přidělí ``application.id``
       (Python default ``uuid4``), který je potřeba pro cizí klíč v
       ``classification_log`` a pro ``entity_id`` auditu.
    3. Audit ``APP_CREATED`` (R5.9). ``changed_fields`` se u vzniku nevyplňuje —
       vzniká celý záznam, ne výběr změněných polí.
    4. Má-li formulář klasifikaci (R5.7 dovolí i bez ní), zapíše se **až teď**
       přes ``set_classification`` (``source = HUMAN``), nikdy přiřazením
       sloupce (R6.1). Tím se do ``classification_log`` vloží počáteční řádek a
       zapíše audit ``CLASSIFICATION_SET`` (R6.2, R6.9).

    Stav ``DECOMMISSIONED`` při vzniku je odmítnut (``LifecycleTransitionError``)
    — vyřazení je dedikovaná akce, ne způsob, jak založit záznam.
    """
    _reject_decommission_via_edit(form)

    application = Application(
        name=form.name,
        description=form.description,
        department=form.department,
        lifecycle_state=str(form.lifecycle_state),
        owner_user_id=form.owner_user_id,
        deputy_user_id=form.deputy_user_id,
        tech_admin_user_id=form.tech_admin_user_id,
        ai_model=form.ai_model,
        created_by_user_id=getattr(actor, "id", None),
    )
    # Klasifikaci NIKDY nenastavujeme přiřazením sloupce — jde přes
    # write_classification níž (R6.1). Sloupec zůstává None do té doby.
    session.add(application)
    # Flush přidělí application.id (Python default uuid4) potřebné pro FK v
    # classification_log a pro entity_id auditu.
    session.flush()

    audit.app_created(
        session,
        actor,
        entity_id=application.id,
        summary=f"Vytvoření záznamu: {application.name}.",
    )

    # Počáteční klasifikace jen pokud ji formulář nese (R5.7 — smí vzniknout
    # neklasifikovaný). Prochází jediným zapisovačem se source=HUMAN.
    if form.classification is not None:
        set_classification(session, application, actor, form.classification)

    return application


def update_application(
    session: Session,
    actor: AuditActor,
    application: Application,
    form: ApplicationForm,
) -> Application:
    """Upraví existující záznam; audit nese jen názvy změněných polí (R5.9).

    Postup v transakci volajícího (bez commitu):

    1. Odmítne přechod do/z ``DECOMMISSIONED`` běžnou editací
       (``LifecycleTransitionError``) — vyřazení a návrat jsou dedikovaná akce
       (úkol 15.2) a jinak by hrozilo porušení constraintu
       ``decommissioned_at_iff_decommissioned``.
    2. Spočítá **skutečně změněná** nesouvisející pole porovnáním hodnoty z
       formuláře proti aktuální hodnotě záznamu (``_EDITABLE_FIELDS``). Beze
       změny hodnoty se pole do ``changed_fields`` nedostane — audit hlásí jen
       reálné změny.
    3. Aplikuje změny na záznam.
    4. Klasifikaci (pokud ji formulář nese a liší se od aktuální) směruje přes
       ``set_classification`` (``source = HUMAN``, R6.1), **ne** přiřazením
       sloupce. Změna klasifikace se **nezapočítává** do ``changed_fields``
       editace — má vlastní ``classification_log`` i audit ``CLASSIFICATION_SET``.
    5. Zapíše audit ``APP_UPDATED`` s ``changed_fields`` = **jen názvy**
       změněných polí (R5.9, R8.6). Audit se zapíše i tehdy, když se změnila
       jen klasifikace (aby existoval záznam editace); ``changed_fields`` pak
       může být prázdný a klasifikační změnu nese její vlastní audit.

    Constraint-safety: název už ověřila routa (14.1) proti duplicitě s
    ``exclude_id`` upravovaného záznamu; výčty a existence osob rovněž. Tato
    vrstva jen zapisuje.
    """
    _reject_decommission_via_edit(form)

    # Blokace návratu ze stavu DECOMMISSIONED běžnou editací: čištění
    # decommissioned_at řeší dedikovaná akce (úkol 15.2). Kdyby byl záznam
    # vyřazený a formulář by chtěl jiný stav, šlo by o reaktivaci — mimo tuto
    # cestu.
    if application.lifecycle_state == str(LifecycleState.DECOMMISSIONED):
        raise LifecycleTransitionError(
            "Návrat ze stavu Vyřazená se neprovádí přes formulář — použij "
            "dedikovanou akci (vyhrazenou roli Admin)."
        )

    changed_fields: list[str] = []
    for field in _EDITABLE_FIELDS:
        new_value = _form_value(form, field)
        current_value = getattr(application, field)
        if new_value != current_value:
            setattr(application, field, new_value)
            changed_fields.append(field)

    # Klasifikace: přes jediného zapisovače, ne přiřazením (R6.1). Do
    # changed_fields se nezapočítává — má vlastní log i audit.
    if form.classification is not None:
        if application.classification != str(form.classification):
            set_classification(session, application, actor, form.classification)

    audit.app_updated(
        session,
        actor,
        entity_id=application.id,
        summary=f"Editace záznamu: {application.name}.",
        changed_fields=changed_fields or None,
    )

    return application


# --- Vyřazení a návrat (úkol 15.2, design.md 5.3, R5.12–R5.14) -----------
#
# Přechod do/z stavu ``DECOMMISSIONED`` je **jediné** místo, kde se
# ``decommissioned_at`` a ``decommissioned_by`` mění (běžná editace ho výše
# odmítá kvůli constraint-safety). Obě funkce běží v transakci volajícího bez
# commitu (design.md 6.3) a stav i časovou značku mění **spolu**, aby byl
# constraint ``decommissioned_at_iff_decommissioned`` (database.md 4) splněný
# po celou dobu:
#
# - vyřazení: stav = ``DECOMMISSIONED`` **a zároveň** ``decommissioned_at`` =
#   teď (UTC) + ``decommissioned_by`` = aktér;
# - návrat: stav = platný nevyřazený stav **a zároveň** ``decommissioned_at`` a
#   ``decommissioned_by`` vyprázdněné (R5.14), aby retenční lhůta začala znovu
#   až při dalším vyřazení.
#
# Audit vzniká ve stejné transakci jako změna (design.md 5.2): vyřazení píše
# ``APP_DECOMMISSIONED`` (R5.13), návrat ``APP_REACTIVATED`` (R5.14). Oprávnění
# „jen Admin" (R5.12) vynucuje HTTP guard ``require_decommission``; tyto funkce
# ho už znovu neověřují (autorizace míří do vrstvy ``auth``, ne ``services`` —
# design.md sekce 1), jen odmítnou nesmyslný přechod (dvojí vyřazení, návrat
# nevyřazeného) jasnou ``LifecycleTransitionError``.

#: Cílový stav návratu z vyřazení. Záznam si předchozí stav nepamatuje
#: (database.md 4 žádný takový sloupec nemá), takže se návrat vrací do jednoho
#: rozumného stavu. Vyřazení je konec životního cyklu produkční aplikace, proto
#: je návratem ``IN_PRODUCTION`` — aplikace se vrací do provozu. Funkce ho bere
#: jako výchozí hodnotu parametru, aby šel v případě potřeby přebít.
_REACTIVATE_TARGET_STATE = LifecycleState.IN_PRODUCTION


def decommission_application(
    session: Session,
    actor: AuditActor,
    application: Application,
) -> Application:
    """Vyřadí záznam do stavu ``Vyřazená`` (R5.12, R5.13, design.md 5.3).

    V transakci volajícího (bez commitu) nastaví **současně** stav
    ``DECOMMISSIONED``, ``decommissioned_at`` na aktuální čas (UTC) a
    ``decommissioned_by`` na identitu aktéra, takže constraint
    ``decommissioned_at_iff_decommissioned`` (database.md 4) zůstává splněný.
    Ve stejné transakci zapíše audit ``APP_DECOMMISSIONED`` (R5.13), aby
    nevznikla změna bez auditu.

    Oprávnění „jen Admin" (R5.12) vynucuje HTTP guard ``require_decommission``
    — tato funkce ho neopakuje (design.md sekce 1). Už vyřazený záznam odmítne
    ``LifecycleTransitionError`` (dvojí vyřazení je chybná akce a druhé
    vyřazení by přepsalo původní ``decommissioned_at``, a tím posunulo
    retenční lhůtu).
    """
    if application.lifecycle_state == str(LifecycleState.DECOMMISSIONED):
        raise LifecycleTransitionError(
            "Záznam je už vyřazený — opakované vyřazení nedává smysl."
        )

    # Stav a časovou značku měníme spolu, aby constraint platil po celou dobu.
    application.lifecycle_state = str(LifecycleState.DECOMMISSIONED)
    application.decommissioned_at = datetime.now(timezone.utc)
    application.decommissioned_by = getattr(actor, "id", None)

    audit.app_decommissioned(
        session,
        actor,
        entity_id=application.id,
        summary=f"Vyřazení záznamu: {application.name}.",
    )

    return application


def reactivate_application(
    session: Session,
    actor: AuditActor,
    application: Application,
    new_state: LifecycleState = _REACTIVATE_TARGET_STATE,
) -> Application:
    """Vrátí záznam ze stavu ``Vyřazená`` a vyprázdní časovou značku (R5.14).

    V transakci volajícího (bez commitu) nastaví **současně** platný
    nevyřazený stav (výchozí ``IN_PRODUCTION`` — viz ``_REACTIVATE_TARGET_STATE``)
    a **vyprázdní** ``decommissioned_at`` i ``decommissioned_by`` (R5.14), takže
    constraint ``decommissioned_at_iff_decommissioned`` zůstává splněný a
    retenční lhůta začne znovu až při dalším vyřazení. Ve stejné transakci
    zapíše audit ``APP_REACTIVATED`` (R5.14).

    Oprávnění „jen Admin" (R5.12) vynucuje HTTP guard ``require_decommission``.
    Cílový stav ``new_state`` nesmí být ``DECOMMISSIONED`` (to by nebyl návrat)
    a záznam musí být aktuálně vyřazený — jinak ``LifecycleTransitionError``.
    """
    if application.lifecycle_state != str(LifecycleState.DECOMMISSIONED):
        raise LifecycleTransitionError(
            "Návrat z vyřazení lze provést jen u vyřazeného záznamu."
        )
    if new_state is LifecycleState.DECOMMISSIONED:
        raise LifecycleTransitionError(
            "Návrat z vyřazení musí mířit do nevyřazeného stavu."
        )

    # Stav a vyprázdnění časové značky měníme spolu, aby constraint platil.
    application.lifecycle_state = str(new_state)
    application.decommissioned_at = None
    application.decommissioned_by = None

    audit.app_reactivated(
        session,
        actor,
        entity_id=application.id,
        summary=f"Návrat záznamu z vyřazení: {application.name}.",
    )

    return application
