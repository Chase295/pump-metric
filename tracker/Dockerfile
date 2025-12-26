FROM python:3.11-slim

WORKDIR /app

# Installation der benötigten Pakete
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir asyncpg websockets python-dateutil aiohttp prometheus-client

# Kopiere main.py
COPY main.py .
COPY db_migration.py .

# Port für Health + Metrics freigeben
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Graceful Shutdown
STOPSIGNAL SIGTERM

# Starten
CMD ["python", "-u", "main.py"]


