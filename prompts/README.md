# Prompty

Klíčové prompty použité při stavbě REGINY. Cílem není přepis celé konverzace
s AI, ale zachycení **skutečného zadání a záměru**, který každý artefakt vyrobil.
Autoritativní podobou promptů jsou zadání a specifikace, na které tyto soubory
odkazují.

## Pořadí a smysl

Řešení nevzniklo jedním promptem, ale řízeným postupem: zadání → požadavky →
návrh → rozhraní → databáze → plán úkolů → implementace. Prompty níže sledují
toto pořadí.

| Soubor | Co obsahuje |
|---|---|
| `00-master-prompt.md` | **Master Prompt** — původní zadání předané AI (zadání pro AI) v plném znění, plus název a verze modelu. |
| `10-pozadavky.md` | Prompt, kterým vznikl `requirements.md` (co systém dělá a jaká pravidla platí). |
| `20-navrh.md` | Prompt, kterým vznikl `design.md` (jak se systém postaví — vrstvy, autorizace, nasazení). |
| `30-rozhrani.md` | Prompt, kterým vznikl `ui.md` (inventář obrazovek odvozený ze schválených mocků). |
| `40-databaze.md` | Prompt, kterým vznikl `database.md` (datový model, constrainty, indexy). |
| `50-plan-a-implementace.md` | Prompt, kterým vznikl `tasks.md` a podle kterého probíhala implementace po svislých řezech. |

## Kde jsou autoritativní verze

Pracovními prompty byly ve skutečnosti samotné specifikační dokumenty. Žijí
v repozitáři a jsou verzované:

- Zadání: `Domácí_úkol_—_AI_Implementation_Expert_(zadání).md` v kořeni repozitáře
- Specifikace: `.kiro/specs/app-registry-core/` (`requirements.md`, `design.md`,
  `ui.md`, `database.md`, `tasks.md`)
- Schválené mocky: `design/mocks/`
