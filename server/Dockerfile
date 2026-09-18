FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Stockfish binary + curl for healthchecks
# (Debian installs stockfish to /usr/games, off PATH — symlink it.)
RUN apt-get update && apt-get install -y --no-install-recommends stockfish curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/games/stockfish /usr/local/bin/stockfish \
    && stockfish --help >/dev/null 2>&1 || stockfish quit 2>/dev/null || true

WORKDIR /app

# Build context is the REPO ROOT (see docker-compose.yml).
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
