# Prompt — rozhraní (`ui.md`)

Záměr, který vyrobil inventář obrazovek specifikace `app-registry-core`.
Autoritativní podobou je `.kiro/specs/app-registry-core/ui.md`; předlohou jsou
schválené mocky v `design/mocks/`.

## Zadání pro AI

Ze schválených vizuálních mocků odvoď inventář obrazovek: co je na které
obrazovce, jak se mapuje na požadavky a co z mocků vědomě nepřejímáme.

- **Produktový název:** REGINA — REGistr INterních Aplikací. Podtitul
  s diakritikou (mock ji vynechává), patička `© Home Credit International`.
- **Zdrojové mocky → obrazovky:** Moje aplikace (karty, `/moje`), Průvodce
  registrací (tři kroky), Detail aplikace (s režimem „Pouze pro čtení"),
  Správa registru (tabulka s filtry, `/registr`). Pro obrazovky Uživatelé a
  Auditní logy mock neexistuje — použij vzor tabulky ze Správy registru.
- **Jazyk:** rozhraní celé v češtině; žádné strojové kódy v UI, žádné anglické
  popisky; klasifikace jako `MALÁ / STŘEDNÍ / VELKÁ`.
- **Navigace:** tmavý sidebar; položky Uživatelé a Auditní logy se roli
  Uživatel nevykreslují, ale cesty jsou chráněné na backendu (skrytí je jen
  pohodlnost, ne ochrana).
- Ke každé přejaté obrazovce uveď, co se z mocku **vědomě nepřejímá** a proč
  (notifikace, nastavení, avatary, SLA monitoring, hromadné operace…).
- Poznamenej, že samotné HTML mocky patří verzované do `design/mocks/`.
