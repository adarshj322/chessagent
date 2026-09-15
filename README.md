# Stockfish Move Analyzer

Web app: server-side Stockfish finds the best move, any OpenRouter model explains why — with the user's own API key.

## Structure

- `server/` — FastAPI + Stockfish UCI (`POST /api/analyze`). No LLM keys. LRU cache, concurrency limit, depth cap 28.
- `web/` — Vite + React board, engine panel, BYOK explanation panel with streaming + move verification badge.
- Shared grounding logic mirrored in both: `server/prompt.py` ↔ `web/src/lib/prompt.ts`, `server/verify.py` ↔ `web/src/lib/verify.ts`.

## Quickstart

```bash
# backend (Python 3.11/3.12, needs stockfish binary)
cd server && pip install -r requirements.txt
uvicorn server.app:app --reload --port 8000

# frontend (Node 20+)
cd web && npm install && npm run dev
```

Open http://localhost:5173 → paste/make a position → Analyze → add OpenRouter key → Explain.

## Key decisions

- **Backend Stockfish** (not WASM): deeper depth, shared cache, per your choice.
- **Local-only BYOK**: key in `localStorage`, browser → OpenRouter direct. Backend never sees it.
- **Anti-hallucination**: prompt injects FEN + eval + PV lines with "only cite ENGINE_PVS" rule, `temperature 0.2`, SAN verification badge flags non-engine moves.
- **MVP scope**: single position only. Full-game PGN review is the natural next step.

## Status

Scaffolded MVP. Backend prompt/verify logic tested (`python-chess`); `py_compile` clean.
Full `pytest` + `npm run build` need a standard dev machine (this env lacks Node wheels and FastAPI on Python 3.14).
