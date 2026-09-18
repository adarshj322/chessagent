# Stockfish Move Analyzer

Learn **why** Stockfish plays a move — with engine-grade accuracy, explained for your level.

## The accuracy model (read this first)

LLMs hallucinate chess moves. So this app uses two layers:

1. **Deterministic facts (always correct, no API key needed).** The backend computes, from the real
   board + Stockfish numbers with `python-chess`: what the move *does* (mate / check / capture /
   castle / promotion), exact material swing, tactics created (hanging pieces, pins, forks, discovered
   or double check), the opponent's best reply (taken from the engine PV, never guessed), and why each
   alternative is worse (exact eval loss in pawns). Rendered as **Why this move**.
2. **LLM rephrasing (optional, BYOK).** Any OpenRouter model only *rephrases* those facts for the
   student's rating. The prompt injects FEN + full PVs + verified facts with an "only cite ENGINE_PVS"
   rule at `temperature 0.2`, and a **3-tier verifier** checks every cited move:
   `engine line` (safe) → `legal but not recommended` (amber) → `hallucinated` (red).

There is no such thing as "100% LLM accuracy" — the guarantee here is that **Layer 1 never needs
trust**, and Layer 2 is fenced in by it.

## Structure

- `server/` — FastAPI + persistent Stockfish pool (`POST /api/analyze` returns engine lines **plus**
  the deterministic `explanation`), `POST /api/verify`, TTL-LRU cache, per-IP rate limit, request IDs.
- `web/` — Vite + React board with best-move arrows, PV stepper, verified Why panel, BYOK streaming
  explanation panel with 3-tier badge.
- Shared grounding logic mirrored in both: `server/prompt.py` ↔ `web/src/lib/prompt.ts`,
  `server/verify.py` ↔ `web/src/lib/verify.ts`.

## Quickstart

### Docker (recommended for production)

```bash
docker compose up --build
# web → http://localhost:8080 (nginx serves UI + proxies /api → backend)
# api → http://localhost:8000/api/health
```

### Local dev

```bash
# backend (Python 3.11/3.12, needs stockfish binary)
cd server && pip install -r requirements.txt
cp .env.example .env   # set STOCKFISH_PATH if needed
uvicorn server.app:app --reload --port 8000  # run from repo root

# frontend (Node 20+)
cd web && npm install && npm run dev   # http://localhost:5173
```

Open the app → pick an example (or make moves / paste FEN) → **Analyze** → read **Why this move** →
optionally add an OpenRouter key → **Explain with LLM**.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{ok, version, engine_available, cache, limits}` |
| POST | `/api/analyze` | `{fen, depth≤28, multipv≤5}` → best move, full PVs (SAN+UCI), eval/mate/win%, deterministic `explanation` |
| POST | `/api/verify` | `{text, fen, pv_sans, pv_sequences?}` → 3-tier move citation check |
| DELETE | `/api/cache` | Drop the analysis cache |

Errors: `400` bad FEN, `429` rate limited, `503` engine missing/timeout, `500` engine error.

## Status

Production-hardened: persistent engine pool, TTL cache, rate limiting, request IDs, healthchecks,
Docker + Compose, CI (`pytest` + `tsc`/`vite build`). Full-game PGN review is the natural next step.
