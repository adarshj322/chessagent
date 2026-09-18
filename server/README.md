# Stockfish server — analysis API + deterministic "why"

No LLM keys here. The browser calls OpenRouter directly (BYOK). This service runs
Stockfish and computes **verifiable board facts** (`tactics.py`) that the LLM is only
allowed to rephrase.

## Files

- `app.py` — routes, lifespan (engine pool warmup/shutdown), rate limit, request IDs.
- `engine.py` — persistent UCI pool, full-PV extraction (SAN+UCI, 8 plies), win%, TTL-LRU cache.
- `tactics.py` — deterministic explainer: mate/check/capture/material/tactics/threats/alternatives.
- `prompt.py` / `verify.py` — grounded prompt builders + 3-tier SAN verification (mirrored in frontend).
- `settings.py` — env-driven config. `schemas.py` — Pydantic models.

## Setup (Python 3.11 or 3.12 recommended)

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set STOCKFISH_PATH if needed
```

Install Stockfish:

```bash
# Ubuntu/Debian
sudo apt-get install -y stockfish
# macOS
brew install stockfish
```

## Run (from repo root)

```bash
uvicorn server.app:app --reload --port 8000
# health: GET http://localhost:8000/api/health
```

## Env

See `.env.example`: `STOCKFISH_PATH`, `ENGINE_MAX_CONCURRENT`, `ENGINE_TIMEOUT_S`,
`ENGINE_CACHE_SIZE/TTL_S`, `ENGINE_THREADS`, `ENGINE_HASH_MB`, `CORS_ORIGINS`, `RATE_LIMIT_PER_MIN`.

## Tests

```bash
python -m pytest server/test_app.py -v
```

Covers prompt grounding, 3-tier verification, deterministic tactics (mate + positional cases),
and API validation — all without a Stockfish binary.
