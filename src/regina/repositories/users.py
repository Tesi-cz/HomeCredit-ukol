"""Repozitář osob — minimální dotazy nad `users` (design.md 6.1).

Zde je jen to, co potřebuje párování osoby při přihlášení (design.md 4.2
krok 6). Plná uživatelská služba se správou rolí je úkol 17.2; tento soubor
záměrně nezasahuje do rolí ani nezavádí širší API, aby ho úkol 17.2 mohl
rozšířit, ne přepsat.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from regina.db.models.users import User
from regina.domain.enums import Role


def get_by_oidc_subject(session: Session, subject: str) -> User | None:
    """Najde osobu podle `oidc_subject`. To je po prvním přihlášení trvalá
    identita osoby (database.md 3)."""
    stmt = select(User).where(User.oidc_subject == subject)
    return session.execute(stmt).scalar_one_or_none()


def get_by_email(session: Session, email: str) -> User | None:
    """Najde osobu podle e-mailu bez ohledu na velikost písmen.

    E-mail je spojovací klíč mezi adresářem osob a poskytovatelem identity
    (database.md users). Porovnává se přes `lower(email)`, aby odpovídalo
    funkcionálnímu unikátnímu indexu `uq_users_lower_email`.
    """
    if not email:
        return None
    stmt = select(User).where(func.lower(User.email) == func.lower(email))
    return session.execute(stmt).scalar_one_or_none()


def get_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return session.execute(stmt).scalar_one_or_none()


def get_by_ids(
    session: Session, user_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, User]:
    """Dohledá osoby podle množiny identifikátorů jako mapu ``id → User``.

    Detail záznamu (úkol 15.1) potřebuje zobrazit odpovědnou trojici i aktéry
    historie klasifikace **jménem a pozicí** (R4.3), ale drží jen jejich
    identifikátory (cizí klíče na ``users``). Tato funkce jedním dotazem přeloží
    libovolnou sadu identifikátorů — trojici i aktéry historie dohromady — na
    řádky ``users``, z nichž šablona vezme ``display_name`` a ``job_title``.

    Prázdný vstup nevede na dotaz (vrací prázdnou mapu). Neexistující
    identifikátor se v mapě prostě neobjeví — volající pak zobrazí zástupný
    text místo jména, místo aby detail spadl.

    Porovnává se výhradně identita osoby, nikdy jméno (R2.6): vstupem jsou
    identifikátory z odpovědné trojice a z ``classification_log.actor_user_id``.
    """
    ids = {user_id for user_id in user_ids if user_id is not None}
    if not ids:
        return {}
    rows = session.execute(select(User).where(User.id.in_(ids))).scalars().all()
    return {user.id: user for user in rows}


def active_id_exists(session: Session, user_id: uuid.UUID) -> bool:
    """Existuje aktivní osoba s tímto identifikátorem? (validace odpovědné trojice)

    Odpovědná trojice ve formuláři (úkol 14.1) vybírá osoby z adresáře podle
    identity, ne psaním jména (R2.6, ui.md sekce 6). Než se záznam uloží, ověří
    validace, že vlastník, technický správce i případný zástupce odkazují na
    **aktivní** osobu — jinak by vznikl záznam odpovědný neexistujícím nebo
    deaktivovaným člověkem. Cizí klíč ``ON DELETE RESTRICT`` chrání integritu na
    úrovni databáze, tato funkce dává dřív a v češtině hlášku u konkrétního pole.

    Vrací ``True`` jen pro existující řádek s ``is_active = true``.
    """
    stmt = select(User.id).where(User.id == user_id, User.is_active.is_(True))
    return session.execute(stmt.limit(1)).first() is not None


def list_active(session: Session) -> Sequence[User]:
    """Vrátí aktivní osoby z adresáře, řazené podle zobrazovaného jména.

    Průvodce registrací (úkol 14.3) i editace (14.4) vybírají odpovědnou trojici
    — vlastníka, zástupce a technického správce — **z adresáře podle identity**,
    ne psaním jména (R2.6, R5.5, ui.md sekce 6). Formulářové selecty proto
    potřebují seznam osob, jejichž ``id`` se odešle jako hodnota a ``display_name``
    se ukáže uživateli. Vrací jen aktivní osoby (``is_active = true``), aby se
    nedaly přiřadit deaktivované identity; řazení podle jména dělá výběr čitelným.
    """
    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .order_by(func.lower(User.display_name))
    )
    return session.execute(stmt).scalars().all()


def list_all(session: Session) -> Sequence[User]:
    """Vrátí **všechny** osoby z adresáře, řazené podle zobrazovaného jména.

    Správa uživatelů (úkol 17.2, ui.md sekce 8, R11.1) vypisuje osoby známé
    aplikaci — jméno, e-mail, pozici a roli. Na rozdíl od `list_active` (výběr
    do odpovědné trojice) tu záměrně **nefiltrujeme** podle `is_active`: správce
    má vidět celý adresář, aby mohl posoudit přiřazení rolí i u osob, které se
    dosud nepřihlásily (R11.7) nebo byly deaktivovány. Řazení podle jména dělá
    tabulku čitelnou.

    Rozsah adresáře je malý (osoby ve firmě, ne záznamy aplikací), proto se
    vrací celý seznam bez stránkování — obrazovka nemá filtry ani stránky
    (ui.md sekce 8).
    """
    stmt = select(User).order_by(func.lower(User.display_name))
    return session.execute(stmt).scalars().all()


def count_admins(session: Session) -> int:
    """Spočítá **aktivní** osoby s rolí Admin (R11.5).

    Pojistka posledního správce (`services.users.set_role`) potřebuje vědět,
    kolik správců v systému zbývá, aby nedovolila odebrat poslední adminská
    práva. Počítají se jen aktivní osoby (`is_active = true`): deaktivovaná
    identita se nepřihlásí a nemůže systém spravovat, takže do počtu „živých"
    správců nepatří.
    """
    stmt = select(func.count()).select_from(User).where(
        User.role == str(Role.ADMIN),
        User.is_active.is_(True),
    )
    return int(session.execute(stmt).scalar_one())
