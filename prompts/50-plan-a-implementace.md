# Prompt — plán a implementace (`tasks.md`)

Záměr, který vyrobil implementační plán a podle kterého probíhala stavba.
Autoritativní podobou je `.kiro/specs/app-registry-core/tasks.md`.

## Zadání pro AI

Z požadavků, návrhu, rozhraní a databázového modelu vytvoř postupný plán
implementace a stav podle něj po **svislých řezech**.

- **Pořadí je záměrné:** nejdřív běžící skořápka a nasazení (aby existovalo
  místo, kam přidávat), pak doména a autorizace (na nich stojí každá obrazovka),
  teprve pak jednotlivé obrazovky, každá jako svislý řez od routy po šablonu.
- **Průběžné pravidlo:** po každém dokončeném úseku musí `docker compose up`
  naběhnout a `/health` odpovídat. Rozbitý stav se nepředává dál.
- **Kontrolní body:** vlož checkpointy „aplikace naběhne", „přihlášení funguje",
  „evidence je použitelná" a závěrečné ověření čistého startu, běhu bez
  internetu a nepřítomnosti tajemství.
- **Testy:** označ jako volitelné (`*`); testovací pokrytí se nehodnotí. Výjimka
  je test, že přímý `POST` na cizí záznam projde jen roli Admin i bez tlačítka
  v UI — je to důkaz tvrzení „autorizace na backendu, ne skrytím prvku".
- Každý úkol propoj s číslem požadavku, který plní.

## Poznámka k implementaci

Během stavby se objevila zjištění, která jsou zaznamenaná přímo v úkolech
(např. issuer Dexu musí být tatáž adresa pro prohlížeč i kontejner —
`host.docker.internal`; Dex u statických účtů nevydává claim se skupinami,
takže roli Admin přiděluje seed). Odchylky od návrhu jsou přiznané v hlavním
`README.md`, sekce *Vědomý dluh*.
