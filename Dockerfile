# REGINA — sestavení image
#
# Dva stupně. Node přeloží Tailwind do jednoho CSS souboru, Python stupeň
# nainstaluje připnuté závislosti a přeložené CSS převezme. Node se do běhového
# prostředí nedostane.
#
# V žádném stupni nejsou tajemství. Veškerá konfigurace přichází za běhu
# proměnnými prostředí (R12.4).

# --- Stupeň 1: rozhraní ------------------------------------------------------
FROM node:22-alpine AS ui

WORKDIR /build

# Nejdřív jen manifesty, aby se vrstva s závislostmi znovu použila, když se
# změní jen zdrojové soubory.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tailwind.config.js ./
COPY src/regina/web/templates ./src/regina/web/templates
COPY src/regina/web/static/css/input.css ./src/regina/web/static/css/input.css

RUN npx tailwindcss \
      -i ./src/regina/web/static/css/input.css \
      -o /build/app.css \
      --minify

# --- Stupeň 2: běhové prostředí ---------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Aplikace neběží jako root.
RUN groupadd --system regina \
 && useradd --system --gid regina --create-home --home-dir /home/regina regina

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Zdrojový strom včetně self-hostovaných fontů (R13.9) — fonty leží ve
# `src/regina/web/static/fonts/` a jsou verzované, takže se zkopírují spolu se
# zbytkem `src`. Žádný samostatný krok pro fonty proto není potřeba.
COPY src ./src

# Konfigurace Alembic. Entrypoint podle ni pri startu spusti `alembic upgrade
# head` jeste pred serverem (R12.8). script_location v alembic.ini je relativni
# (src/regina/db/migrations), takze funguje s WORKDIR /app a zkopirovanym src.
COPY alembic.ini ./alembic.ini

# Přeložené CSS z prvního stupně.
COPY --from=ui /build/app.css ./src/regina/web/static/css/app.css

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh \
 && chown -R regina:regina /app

USER regina

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["serve"]
