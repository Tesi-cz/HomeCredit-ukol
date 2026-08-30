# Prompt — poradce klasifikace

Systémový prompt, který se za běhu posílá jazykovému modelu při návrhu
klasifikace (funkce klasifikačního poradce, spec `classification-advisor`).
Autoritativní podobou je konstanta `CLASSIFY_SYSTEM_PROMPT` v
`src/regina/services/advisor.py` — tento soubor ji zrcadlí pro dohledatelnost.

## Kontext použití

- **Kdy:** uživatel ve formuláři aplikace vyplní dotazník o šesti dimenzích
  (počet uživatelů, citlivost dat, kritičnost, integrace, regulace, míra AI)
  a vyžádá si doporučení.
- **Jak:** volání jde **výhradně** přes vlastní abstrakci (`src/regina/llm/`),
  nikdy přímo z aplikačního kódu. Poskytovatel je zaměnitelný konfigurací
  (OpenRouter / firemní AI Gateway / mock).
- **Vstup je anonymizovaný:** volitelná poznámka projde anonymizací
  (jméno/e-mail/telefon → zástupný symbol) **před** odesláním; zdůvodnění se po
  návratu rehydratuje.
- **Fallback:** když model není dostupný nebo selže, použije se deterministické
  bodové skóre a zdůvodnění se poskládá bez modelu.

## Systémový prompt (české znění)

> Jsi asistent pro klasifikaci interních firemních aplikací ve finanční
> instituci. Na základě odpovědí dotazníku doporučíš velikostní klasifikaci
> MALÁ, STŘEDNÍ, nebo VELKÁ a stručně ji zdůvodníš česky (2–4 věty). Vstup může
> obsahovat zástupné symboly typu `[[JMENO_1]]` nebo `[[EMAIL_1]]` — ponech je
> beze změny, nedoplňuj za ně konkrétní údaje. Odpovíš čistým zdůvodněním bez
> nadpisů.

## Uživatelský prompt (skládá se za běhu)

Sestavuje ho `advisor._build_user_prompt`: seznam otázek a jejich bodového
hodnocení, celkové skóre, deterministické bodové doporučení a — je-li zadaná —
anonymizovaná poznámka. Konkrétní texty otázek a odpovědí jsou v
`src/regina/domain/questionnaire.py`.
