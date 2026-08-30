# Prompt — požadavky (`requirements.md`)

Záměr, který vyrobil dokument požadavků specifikace `app-registry-core`.
Autoritativní podobou je samotný `.kiro/specs/app-registry-core/requirements.md`.

## Zadání pro AI

Ze zadání (varianta A — Registr interních aplikací) vytvoř dokument požadavků,
který popisuje **co** systém dělá a **jaká pravidla platí**, ne volbu
frameworků ani API kontrakty. Drž se těchto mantinelů:

- **Identita:** přihlášení výhradně přes OIDC, žádná tabulka hesel; dvě role
  (Uživatel, Správce) s odlišnými právy; autorizace vynucená na backendu, ne
  skrytím prvků v UI.
- **Doména:** záznam aplikace nese název, popis, odpovědnou trojici (vlastník,
  zástupce, technický správce), útvar, klasifikaci `MALÁ / STŘEDNÍ / VELKÁ`,
  stav životního cyklu a použitý AI model. Klasifikaci vždy zadává člověk a
  každá změna jde do nemazatelné historie.
- **Práva:** Uživatel spravuje jen záznamy, kde je členem trojice; Správce
  spravuje vše, přepisuje klasifikaci s povinným důvodem, vyřazuje záznamy,
  spravuje role, čte audit.
- **Audit a retence:** nemazatelná auditní stopa; definovaná retenční politika.
- **Rozsah:** jazykový model do tohoto dokumentu **nepatří** — návrh
  klasifikace modelem je oddělený do navazující specifikace
  `classification-advisor`. Jádro musí být kompletní i bez něj a připravené
  doplnit poradce čistě aditivně.
- Uveď sekci vědomého dluhu: co se do jádra vědomě nedělá a proč.

Formát: EARS-style akceptační kritéria seskupená do číslovaných požadavků.
