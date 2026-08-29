# Schválené vizuální mocky

Tato složka archivuje **schválenou vizuální předlohu** REGINY. Slouží jako
verzovaná reference, podle které se stavěly šablony běžící aplikace
(`src/regina/web/templates/`). Design ani vzhled nejsou hodnocenou oblastí —
mocky jsou zde pro dohledatelnost rozhodnutí, ne jako dodávka.

## Soubory

| Soubor | Co je to |
|---|---|
| `prototyp.html` | Kompletní vizuální prototyp všech obrazovek v jednom souboru. |

## Jak prototyp otevřít

`prototyp.html` je samostatný soubor — stačí ho otevřít v prohlížeči. Přepínání
mezi obrazovkami je v levém menu (sidebar). Pro pohodlné otevření bez build
kroku tahá prototyp fonty z Google Fonts a ikony z Lucide přes CDN.

> **Pozor:** tato CDN závislost platí **jen pro prototyp**. Běžící aplikace
> používá výhradně self-hostované fonty a ikony bez připojení k internetu
> (požadavek R13.9) — fonty z `/static/fonts/*.woff2`, ikony z SVG sprite
> `/static/icons/icons.svg`.

## Které obrazovky mocky pokrývají

Prototyp obsahuje čtyři schválené obrazovky (viz také `.kiro/specs/app-registry-core/ui.md`, sekce 2):

| Obrazovka v prototypu | Odpovídá v aplikaci |
|---|---|
| Uživatelský portál — Moje aplikace (karty) | `/moje` |
| Průvodce registrací aplikace (tři kroky) | registrace / editace záznamu |
| Detail aplikace (s režimem „Pouze pro čtení") | `/registr/{id}` |
| Správa registru aplikací (tabulka s filtry) | `/registr` |

Pro obrazovky **Uživatelé** a **Auditní logy** samostatný mock neexistuje —
přebírají vzor tabulky ze Správy registru.

## Vědomé odchylky prototypu od běžící aplikace

Prototyp je **předloha, ne závazný obraz**. Při stavbě šablon se vědomě lišíme:

- **Jazyk a klasifikace.** Anglické popisky a označení úrovní z prototypu jsou
  v aplikaci přeložené do češtiny a klasifikace používá `MALÁ / STŘEDNÍ / VELKÁ`
  (rozhodnuto dříve v návrhu). Rozhraní běžící aplikace je celé česky.
- **Diakritika v podtitulu.** V prototypu je podtitul bez diakritiky
  („REGistr INternich Aplikaci"); správná varianta v aplikaci je s diakritikou.
- **Prvky mimo rozsah jádra.** Notifikace, Nastavení, avatary, monitoring SLA,
  hromadné operace a další prvky viditelné v prototypu se vědomě neimplementují —
  zdůvodnění je v hlavním `README.md`, sekce *Vědomý dluh*.

Detailní inventář obrazovek a mapování na požadavky je v
`.kiro/specs/app-registry-core/ui.md`.
