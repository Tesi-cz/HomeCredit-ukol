"""Výpočet stránkování pro tabulkové výpisy (ui.md sekce 5, R3.5).

Stránkování se objevuje na více obrazovkách (Registr, Auditní logy), a text
„Zobrazeno 1–20 z 128 záznamů" i logika předchozí/další stránky musí být
všude stejná. Proto je matematika tady, v jedné čisté funkci bez závislosti na
HTTP i na databázi, a šablona jen vykreslí výsledek přes komponentu
`components/pagination.html`.

Routy tedy stránkování nepočítají ručně — načtou celkový počet z repozitáře,
zavolají `paginate(...)` a předloženou `Pagination` předají kontextu. Komponenta
z ní vezme rozsah („from–to"), celkový počet a čísla stránek.

Modul je záměrně bez závislostí na zbytku aplikace (jako `domain/`), aby se dal
snadno otestovat a použít kdekoli.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pagination:
    """Vypočtený stav stránkování pro jednu obrazovku.

    - `page` je aktuální stránka (od 1),
    - `page_size` je počet záznamů na stránku,
    - `total` je celkový počet záznamů přes všechny stránky,
    - `total_pages` je počet stránek (nejméně 1, i pro prázdný výpis),
    - `from_index`/`to_index` je rozsah zobrazených záznamů (od 1); u prázdného
      výpisu obojí 0, aby text zněl „Zobrazeno 0–0 z 0 záznamů",
    - `pages` je seznam čísel stránek k vykreslení (okno kolem aktuální).
    """

    page: int
    page_size: int
    total: int
    total_pages: int
    from_index: int
    to_index: int
    pages: tuple[int, ...]

    @property
    def has_previous(self) -> bool:
        """Existuje předchozí stránka? (řídí stav tlačítka „Předchozí")."""
        return self.page > 1

    @property
    def has_next(self) -> bool:
        """Existuje další stránka? (řídí stav tlačítka „Další")."""
        return self.page < self.total_pages

    @property
    def previous_page(self) -> int:
        """Číslo předchozí stránky (nikdy pod 1)."""
        return max(1, self.page - 1)

    @property
    def next_page(self) -> int:
        """Číslo další stránky (nikdy nad poslední)."""
        return min(self.total_pages, self.page + 1)

    @property
    def is_empty(self) -> bool:
        """Je výpis prázdný? (žádné záznamy k zobrazení)."""
        return self.total == 0


def paginate(
    *,
    total: int,
    page: int = 1,
    page_size: int = 20,
    window: int = 5,
) -> Pagination:
    """Spočítá stav stránkování z celkového počtu a aktuální stránky.

    `total` a `page` se defenzivně ořežou na platný rozsah: záporný celkový
    počet je 0, `page` se sevře mezi 1 a poslední stránku. Tím routa nemusí
    hlídat, že přišlo `?page=999` nebo `?page=-1` z URL — funkce vrátí platný
    stav a odkazy nikdy nemíří mimo rozsah.

    `window` je maximální počet čísel stránek k vykreslení; okno se centruje
    kolem aktuální stránky a posune se, aby se nevešlo mimo rozsah.
    """
    if page_size < 1:
        page_size = 1
    if total < 0:
        total = 0

    total_pages = max(1, (total + page_size - 1) // page_size)

    # Sevření aktuální stránky do platného rozsahu — obrana proti hodnotě z URL.
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    if total == 0:
        from_index = 0
        to_index = 0
    else:
        from_index = (page - 1) * page_size + 1
        to_index = min(page * page_size, total)

    pages = _page_window(page, total_pages, window)

    return Pagination(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        from_index=from_index,
        to_index=to_index,
        pages=pages,
    )


def _page_window(page: int, total_pages: int, window: int) -> tuple[int, ...]:
    """Vrátí souvislé okno čísel stránek kolem aktuální stránky.

    Okno má nejvýše `window` položek. Pokud je stránek méně, vrátí všechny.
    Jinak se centruje na aktuální stránku a přisune k okraji, aby zůstalo
    souvislé a plné i na začátku a na konci rozsahu.
    """
    if window < 1:
        window = 1
    if total_pages <= window:
        return tuple(range(1, total_pages + 1))

    half = window // 2
    start = page - half
    if start < 1:
        start = 1
    end = start + window - 1
    if end > total_pages:
        end = total_pages
        start = end - window + 1

    return tuple(range(start, end + 1))
