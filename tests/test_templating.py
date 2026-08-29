"""Testy šablonovací vrstvy (úkol 8.5, R13.2, R13.3).

Ověřují jediný vstupní bod pro formátování data (DD.MM.YYYY a DD.MM.YYYY HH:MM)
včetně ošetření `None`, a že se filtry i globály zaregistrují do prostředí
Jinja2. Renderování `lang="cs"` a sbalení sidebaru na 1024 px se ověřuje nad
statickými šablonami.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from regina.web.templating import build_templates, datum, datum_cas

_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "regina" / "web" / "templates"


def test_datum_formats_date_as_ddmmyyyy() -> None:
    assert datum(date(2024, 3, 9)) == "09.03.2024"


def test_datum_accepts_datetime_and_drops_time() -> None:
    assert datum(datetime(2024, 12, 1, 15, 4)) == "01.12.2024"


def test_datum_none_returns_dash() -> None:
    assert datum(None) == "—"


def test_datum_cas_formats_datetime_with_time() -> None:
    assert datum_cas(datetime(2024, 3, 9, 8, 5)) == "09.03.2024 08:05"


def test_datum_cas_none_returns_dash() -> None:
    assert datum_cas(None) == "—"


def test_filters_and_globals_are_registered() -> None:
    """Filtr `datum`/`datum_cas` i jejich globální varianta musí být v prostředí."""
    templates = build_templates()
    assert templates.env.filters["datum"] is datum
    assert templates.env.filters["datum_cas"] is datum_cas
    assert templates.env.globals["datum"] is datum
    assert templates.env.globals["datum_cas"] is datum_cas


def test_datum_filter_renders_in_template() -> None:
    templates = build_templates()
    rendered = templates.env.from_string("{{ hodnota | datum }}").render(hodnota=date(2024, 3, 9))
    assert rendered == "09.03.2024"


def test_base_and_error_layout_declare_czech_language() -> None:
    """Každá vykreslená stránka musí mít <html lang="cs"> (R13.2)."""
    for name in ("base.html", "errors/error_layout.html"):
        html = (_TEMPLATES_DIR / name).read_text(encoding="utf-8")
        assert '<html lang="cs">' in html


def test_sidebar_collapses_below_desktop_breakpoint() -> None:
    """Sidebar je pod 1024 px sbalený a od tokenu `desktop` statický (R13.10)."""
    html = (_TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    # Výchozí (mobilní) stav: sidebar odsunutý mimo obrazovku.
    assert "-translate-x-full" in html
    # Od 1024 px (token `desktop`) statický a viditelný.
    assert "desktop:static" in html
    assert "desktop:translate-x-0" in html
