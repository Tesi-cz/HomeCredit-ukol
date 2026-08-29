"""Navigace sidebaru jako jediný zdroj pravdy (R13.5, ui.md sekce 3).

Sidebar má čtyři položky a jednu primární akci. Definují se **jednou**, tady,
a šablona `base.html` je vykresluje ve smyčce. Žádná routa ani šablona
nepřepisuje seznam podruhé; kdyby to udělala, rozešel by se stav aktivní
položky nebo viditelnost s tím, co je zapsané.

**Aktivní položka.** Nezná ji šablona z pevného textu na stránce — každá routa
předá kontextu klíč `active_nav` (např. `"registr"`), a šablona porovná klíč
proti položkám. Zvýrazní se ta, jejíž `key` se shoduje. Prázdný `active_nav`
(žádná shoda) je legitimní stav pro obrazovky mimo hlavní navigaci (např.
průvodce registrací, který sidebar ani nemá — ui.md sekce 6).

**Viditelnost podle role.** Položky Uživatelé a Auditní logy vidí jen Admin
(ui.md sekce 3, R13.6). Skrytí je *pohodlnost* nad vynucením na backendu, ne
ochrana — cesty `/uzivatele` a `/audit` mají vlastní guardy (R2.5). Rozhodnutí,
zda položku ukázat, dělá `can_view` proti roli aktéra, aby se pravidlo
viditelnosti drželo u definice položky, ne rozstrkané v šabloně.
"""

from __future__ import annotations

from dataclasses import dataclass

from regina.domain.enums import Role


@dataclass(frozen=True)
class NavItem:
    """Jedna položka sidebaru.

    `key` je stabilní identifikátor pro porovnání s `active_nav` (nezávislý na
    českém popisku i na cestě). `icon` je id symbolu ve spritu
    `/static/icons/icons.svg`. `admin_only` řídí viditelnost pro roli User.
    """

    key: str
    label: str
    href: str
    icon: str
    admin_only: bool = False

    def can_view(self, role: Role) -> bool:
        """Smí daná role položku vidět v sidebaru? (ui.md sekce 3, R13.6)

        Admin vidí vše. User nevidí položky označené `admin_only`. Toto je jen
        vizuální pohodlnost — cesty jsou chráněné guardy na backendu (R2.5).
        """
        return role == Role.ADMIN or not self.admin_only


#: Jediný zdroj pravdy pro navigaci sidebaru (ui.md sekce 3).
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(key="moje", label="Moje aplikace", href="/moje", icon="moje-aplikace"),
    NavItem(key="registr", label="Registr", href="/registr", icon="registr"),
    NavItem(
        key="uzivatele",
        label="Uživatelé",
        href="/uzivatele",
        icon="uzivatele",
        admin_only=True,
    ),
    NavItem(
        key="audit",
        label="Auditní logy",
        href="/audit",
        icon="audit",
        admin_only=True,
    ),
)


@dataclass(frozen=True)
class PrimaryAction:
    """Primární akce pod navigací — „Nová aplikace" (ui.md sekce 3)."""

    label: str
    href: str
    icon: str


#: Primární akce sidebaru. Cesta registrace nového záznamu (ui.md sekce 6).
PRIMARY_ACTION = PrimaryAction(
    label="Nová aplikace",
    href="/registr/nova",
    icon="nova-aplikace",
)


def visible_nav_items(role: Role) -> tuple[NavItem, ...]:
    """Vrátí položky navigace viditelné pro danou roli.

    Filtr je pohodlnost nad vynucením na backendu (R2.5): skryté cesty zůstávají
    chráněné guardy. Volá ho helper kontextu šablon, aby routy seznam
    neredeklarovaly.
    """
    return tuple(item for item in NAV_ITEMS if item.can_view(role))
