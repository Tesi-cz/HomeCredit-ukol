"""Správa aplikačních rolí osob (design.md 5, R11).

Tohle je **jediné** místo, které mění `users.role`. Obrazovka správy uživatelů
(úkol 17.2, ui.md sekce 8) i případná budoucí interní volání procházejí sem —
žádná routa roli nenastavuje napřímo. Smysl je stejný jako u
`services/classification.py`: změna a její auditní záznam vznikají atomicky, v
**jedné transakci** volajícího. Funkce sama **necommituje** (design.md 6.3);
o transakci se stará vrstva, která ji volá (`get_session`), takže se změna role
a auditní záznam `ROLE_CHANGED` potvrdí společně, nebo vůbec.

**Co služba dělá.** `set_role` nastaví novou roli dotčené osobě a označí, že
role byla nastavena **lokálně** (`role_source = LOCAL`), protože ji tady zapsal
správce ručně. Při reálném poskytovateli identity má claim přednost (R11.6);
lokální přepis je tedy zaznamenaný jako lokální zdroj. Zároveň zapíše auditní
záznam `ROLE_CHANGED` s entitou = dotčený uživatel a českým souhrnem (R11.4).

**Co služba NEdělá.** Nezakládá ani nemaže identity — to zůstává na poskytovateli
identity (R11.3). `set_role` pracuje výhradně nad **existující** osobou předanou
volajícím.

**Pojistka posledního správce (R11.5).** Zvolené pravidlo:

    Změna role je odmítnuta, pokud by po ní v systému nezůstal žádný aktivní
    správce. Konkrétně: měníme-li aktivní osobu s rolí Admin na jinou roli a
    tato osoba je **posledním** aktivním správcem (`count_admins() <= 1`),
    operace se odmítne výjimkou `LastAdminError`.

Toto pravidlo pokrývá i sebe-odebrání (self-demotion): pokud se poslední správce
pokusí odebrat roli sám sobě, `count_admins()` vrátí 1 a změna se zamítne.
Formulace je záměrně obecná — nejde jen o „vlastní" roli aktéra, ale o kohokoli,
kdo je posledním správcem, aby nešlo zlikvidovat správu ani přes cizí účet.
Odebrání role jednomu ze **dvou** správců projde (po změně zůstává jeden).

Rozhraní pojistku odráží tím, že vlastní přepínač zamítne (ui.md sekce 8:
„Vlastní roli si správce odebrat nemůže, akce je nedostupná"), ale skutečné
vynucení je **zde**, na backendu — nezávisle na tom, co se vykreslí.
"""

from __future__ import annotations

# Session se importuje jen pro typovou anotaci; funkce transakci nevytváří.
from sqlalchemy.orm import Session

from regina.db.models.users import User
from regina.domain.enums import Role, RoleSource
from regina.repositories import users as users_repo
from regina.services import audit
from regina.services.audit import AuditActor


class LastAdminError(Exception):
    """Změna role by odebrala poslední adminská práva v systému (R11.5).

    Service-level výjimka — **záměrně** není HTTP chyba ani `AuthorizationError`
    z `auth/deps`. Vrstva `services` nesmí záviset na `auth` ani na HTTP
    (design.md sekce 1). Vyhazuje ji `set_role`, když by změnou nezůstal žádný
    aktivní správce; routa ji přeloží na české chybové hlášení a přesměrování
    zpět (Post/Redirect/Get). Existence pojistky i mimo HTTP je obrana do
    hloubky: platí i pro volání z testů a z případných budoucích interních cest.
    """


def set_role(
    session: Session,
    actor: AuditActor,
    target_user: User,
    new_role: Role,
) -> User:
    """Nastaví aplikační roli osoby a zapíše audit `ROLE_CHANGED` (R11.2, R11.4).

    V jedné transakci volajícího (bez commitu, design.md 6.3):

    1. **Pojistka posledního správce (R11.5).** Odebírá-li se role Admin (nová
       role není Admin, dosavadní byla Admin) a dotčená osoba je posledním
       aktivním správcem (`count_admins() <= 1`), operace se odmítne
       `LastAdminError` a **nic** se nezapíše. Pokrývá i sebe-odebrání, protože
       poslední správce se sám sebe týká (viz modul).
    2. Nastaví `target_user.role = new_role` a `role_source = LOCAL` — roli
       zapsal správce lokálně (R11.6: při reálném poskytovateli má claim
       přednost, lokální přepis je zdroj `LOCAL`).
    3. Zapíše auditní záznam `ROLE_CHANGED` s entitou = dotčený uživatel a
       českým souhrnem (R11.4), ve stejné transakci jako změna.

    Když se nová role rovná dosavadní, změna je bezvýznamná: nezapisuje se ani
    audit (žádná změna se nestala) a vrací se osoba beze změny. Pojistka
    posledního správce se v tom případě neuplatní — role Admin se neodebírá.

    Do auditu se předává **jen** jméno změněného atributu (`role`), nikdy
    hodnota role — hodnoty se do auditu nesmějí dostat (R8.6). Zapisovač `record`
    to i tak vynutí, ale předáváme rovnou jen názvy.

    Parametry:
        session: probíhající transakce volajícího (bez commitu).
        actor: přihlášená osoba provádějící změnu (`id`, `email`, `name` pro
            audit). Autorizaci „jen Admin" vynucuje HTTP guard
            `require_manage_roles` (R11.2); tato funkce ji nepřebírá.
        target_user: dotčená osoba (řádek `users` načtený v této session).
        new_role: nová aplikační role.

    Vrací dotčenou osobu (pro navázání v testech a v routě).

    Vyvolá:
        LastAdminError: změna by odebrala poslední adminská práva (R11.5).
    """
    current_role = Role(target_user.role)

    # Idempotence: shodná role = žádná změna. Nic nezapisujeme (ani audit) a
    # pojistka se neuplatní, protože se role Admin neodebírá.
    if current_role == new_role:
        return target_user

    # 1) Pojistka posledního správce (R11.5). Uplatní se jen při odebírání role
    # Admin (Admin → jiná role). Když je dotčená osoba posledním aktivním
    # správcem, změnu odmítneme dřív, než cokoli zapíšeme.
    removing_admin = current_role == Role.ADMIN and new_role != Role.ADMIN
    if removing_admin and users_repo.count_admins(session) <= 1:
        raise LastAdminError(
            "V systému musí zůstat alespoň jeden správce — poslední adminská "
            "práva nelze odebrat (R11.5)."
        )

    # 2) Zápis role. Roli zde nastavil správce ručně, proto zdroj LOCAL (R11.6).
    target_user.role = str(new_role)
    target_user.role_source = str(RoleSource.LOCAL)

    # 3) Audit ve stejné transakci (design.md 5.2, R11.4). Entita je dotčený
    # uživatel; do changed_fields jen název atributu, nikdy hodnota role (R8.6).
    audit.role_changed(
        session,
        actor,
        entity_id=target_user.id,
        summary=(
            f"Změna role osoby {target_user.display_name} "
            f"({target_user.email})."
        ),
    )

    return target_user
