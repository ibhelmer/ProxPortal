# Copyright 2026 Ib Helmer Nielsen
# SPDX-License-Identifier: Apache-2.0
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/data/labportalen.sqlite3
WORKDIR /app
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt \
    && groupadd --gid 10001 portal \
    && useradd --uid 10001 --gid portal --no-create-home portal \
    && mkdir -p /data && chown portal:portal /data
COPY --chown=portal:portal app ./app
COPY --chown=portal:portal manage.py ./manage.py
COPY LICENSE NOTICE ./
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
