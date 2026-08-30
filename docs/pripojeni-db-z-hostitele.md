# Připojení k databázi z hostitele (PostgreSQL extension)

Databáze `db` v `docker-compose.yaml` **záměrně nepublikuje port** na hostitele —
dosáhne na ni jen kontejner `app` po interní síti compose. To je správně: odpadá
tím kolize s případným Postgresem, který už na hostiteli na portu 5432 běží.

Když se ale potřebuješ na databázi podívat z PostgreSQL extension (nebo z DBeaveru,
psql apod.), otevřeš si dočasný tunel. `docker-compose.yaml` přitom zůstane
nezměněný a repo čisté.

## Postup

1. Spusť aspoň databázi (pokud už `docker compose up` neběží):

   ```powershell
   docker compose up -d db
   ```

2. V druhém okně otevři tunel. Běží, dokud ho nezavřeš (`Ctrl+C`):

   ```powershell
   docker run --rm -p 5432:5432 --network regina_default `
     alpine/socat tcp-listen:5432,fork,reuseaddr tcp-connect:db:5432
   ```

   Kdyby byl port 5432 na hostiteli obsazený, změň jen levou stranu, např.
   `-p 5433:5432`, a v extension pak zadej port `5433`.

3. V PostgreSQL extension zadej připojení:

   | Pole     | Hodnota                    |
   |----------|----------------------------|
   | Host     | `localhost`                |
   | Port     | `5432`                     |
   | Database | `regina`                   |
   | User     | `regina`                   |
   | Password | viz `POSTGRES_PASSWORD` v `.env` |

   Connection string pro nástroje, které ho chtějí najednou:

   ```
   postgresql://regina:<POSTGRES_PASSWORD>@localhost:5432/regina
   ```

4. Až skončíš, tunel zavři (`Ctrl+C` v okně se `socat`). Port z hostitele zmizí
   a nic nezůstane vystavené.

## Poznámky

- Heslo je uložené v `.env` (klíč `POSTGRES_PASSWORD`), který je v `.gitignore`.
  Do tohoto návodu ho schválně nepíšeme, aby se přes dokumentaci nedostalo do gitu.
- Název sítě `regina_default` odpovídá `name: regina` v `docker-compose.yaml`.
  Ověřit ho můžeš příkazem `docker network ls --filter name=regina`.
- Interní connection string, který používá aplikace, má místo `localhost`
  hostname `db` — viz `DATABASE_URL` v `.env`.
