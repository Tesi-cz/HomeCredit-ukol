# Prompt — návrh (`design.md`)

Záměr, který vyrobil návrhový dokument specifikace `app-registry-core`.
Autoritativní podobou je `.kiro/specs/app-registry-core/design.md`.

## Zadání pro AI

Na základě požadavků navrhni **jak** se systém postaví. Rozhodnutí zdůvodni,
neuváděj jen volbu.

- **Architektura:** serverem vykreslovaná aplikace (ne SPA) ve čtyřech vrstvách
  `web → services → repositories → domain`, závislosti míří dovnitř. Vysvětli,
  proč server-rendering (jeden build, běh bez internetu triviální — R13.9) a
  proč oddělená vrstva `domain` bez závislostí (autorizační pravidla jsou čisté
  funkce testovatelné bez DB a HTTP; **tytéž funkce volá guard i šablona**, aby
  se UI nemohlo rozejít s vynucením).
- **Technologie:** Python 3.12, FastAPI (kvůli dependency injection pro
  autorizaci), Jinja2, SQLAlchemy 2.0 (typovaný styl), Alembic, PostgreSQL,
  Dex jako lokální poskytovatel identity.
- **Identita:** OIDC klient nezná žádnou adresu poskytovatele napevno — jediná
  adresa v konfiguraci je `OIDC_ISSUER`, zbytek endpointů přijde z discovery
  dokumentu; názvy claimů jsou konfigurovatelné. Výměna za Entra ID = jen `.env`.
- **Nasazení:** vše přes `docker compose up` bez ručních kroků; migrace a seed
  automaticky při startu; health endpoint; strukturované logování.
- **Sekce 15:** popiš přesně, kam se aditivně připojí klasifikační našeptávač,
  aniž by se měnil podpis `write_classification`.
