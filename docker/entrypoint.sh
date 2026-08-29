#!/bin/sh
# Vstupní bod kontejneru REGINA.
#
# Databáze je připravená dřív, než se spustí aplikace — zajišťuje to healthcheck
# a `depends_on: condition: service_healthy` v compose. Žádné čekací smyčky zde
# proto nejsou potřeba.
#
# Migrace schématu se aplikují automaticky, bez ručního kroku (R12.8).
# Krok se doplní v úkolu 4.5, kdy vznikne první Alembic revize.

set -eu

case "${1:-serve}" in
  serve)
    if [ -f /app/alembic.ini ]; then
      echo "Aplikuji migrace schematu..."
      alembic -c /app/alembic.ini upgrade head
    fi

    exec uvicorn regina.main:create_app \
      --factory \
      --host 0.0.0.0 \
      --port 8000 \
      --proxy-headers \
      --forwarded-allow-ips '*'
    ;;
  *)
    exec "$@"
    ;;
esac
