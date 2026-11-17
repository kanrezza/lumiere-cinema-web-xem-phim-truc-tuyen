FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim-trixie AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 10001 lumiere \
  && useradd --uid 10001 --gid 10001 --create-home lumiere
WORKDIR /app
COPY requirements.txt ./
# MySQL 8.4 uses caching_sha2_password, including after a cold start.
RUN python -m pip install --no-cache-dir -r requirements.txt cryptography==50.0.2
COPY --chown=lumiere:lumiere manage.py ./
COPY --chown=lumiere:lumiere cinema/ cinema/
COPY --chown=lumiere:lumiere config/ config/
COPY --chown=lumiere:lumiere templates/ templates/
COPY --chown=lumiere:lumiere static/ static/
COPY --chown=lumiere:lumiere deploy/staging/seed.py deploy/staging/start.sh /stage/
COPY --from=frontend --chown=lumiere:lumiere /app/static/bundles/catalog/ static/bundles/catalog/
RUN mkdir -p private_media public_media staticfiles \
  && chown lumiere:lumiere private_media public_media staticfiles
USER lumiere
CMD ["/bin/sh", "/stage/start.sh"]
