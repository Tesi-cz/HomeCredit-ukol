# Prompt — databáze (`database.md`)

Záměr, který vyrobil datový model specifikace `app-registry-core`.
Autoritativní podobou je `.kiro/specs/app-registry-core/database.md`.

## Zadání pro AI

Navrhni datový model, který vynucuje integritu **na úrovni databáze**, ne jen
v aplikaci.

- **Tabulky:** `users`, `applications`, `classification_log`, `audit_log`.
- **Výčty:** ukládej jako `text` s `CHECK` constraintem formulovaným jako
  rozšiřitelný seznam povolených hodnot, ne jako nativní `ENUM` (snazší
  rozšíření bez migrace typu).
- **Invarianty vynucené DB:** povinný důvod u `source = ADMIN_OVERRIDE`;
  `decommissioned_at` vyplněné právě tehdy, když je stav `DECOMMISSIONED`;
  unikátní `lower(name)` a `lower(email)`.
- **Cizí klíče:** kaskáda u `classification_log.application_id`; `RESTRICT` na
  vazby na osoby; `audit_log.entity_id` **bez** cizího klíče, aby auditní
  záznamy přežily smazání aplikace.
- **Indexy:** včetně částečného indexu na nevyřazené záznamy (výchozí výpis je
  bez vyřazených).
- **Aditivnost pro poradce:** model připrav tak, aby ho `classification-advisor`
  doplnil bez zásahu do stávajících sloupců (odkaz na doporučení jako nepovinný).
