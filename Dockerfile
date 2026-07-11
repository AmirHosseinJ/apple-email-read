FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

RUN chmod +x /app/docker/web-entrypoint.sh /app/docker/celery-entrypoint.sh \
    && mkdir -p /app/storage/playwright /app/storage/screenshots \
    && chown -R 1000:1000 /app

USER 1000:1000

EXPOSE 8000

ENTRYPOINT ["/app/docker/web-entrypoint.sh"]
