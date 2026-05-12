FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PHARMALIST_CONFIG=/app/config/docker-defaults.json \
    PHARMALIST_AUDIT_ROOT=/data/audit

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY docker ./docker

RUN chmod +x /app/docker/docker-entrypoint.sh \
    && pip install --no-cache-dir .

ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
CMD ["--help"]