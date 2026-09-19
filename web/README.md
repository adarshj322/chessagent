# Web — Stockfish Move Analyzer (Vite + React + TS)

Board + engine panel + **verified Why panel** + OpenRouter BYOK explanation. Your API key stays in
`localStorage` and is sent only to `openrouter.ai`, never to the backend.

## Setup (Node 20+)

```bash
cd web
npm install
cp .env.example .env   # optional: VITE_API_URL=http://localhost:8000
npm run dev            # http://localhost:5173
```

Backend proxy is preconfigured (`vite.config.ts` proxies `/api` → `localhost:8000`),
so dev works with an empty `VITE_API_URL`. For production set
`VITE_API_URL=https://your-api-host` (or serve behind the provided nginx, which
proxies `/api` same-origin).

## Flow

1. Move pieces / paste FEN / pick an example → **Analyze** → `POST /api/analyze`.
2. Read **Why this move** — deterministic engine facts, always correct, no key needed.
3. Click a PV line, step **Next/Prev** to walk the variation on the board (green arrow = best,
   orange = second line).
4. Enter OpenRouter key → **Validate + load models** → pick any model.
5. **Explain with LLM** → streams a rating-aware rephrasing of the verified facts; cited moves get a
   3-tier badge: engine line (green) / legal-but-not-recommended (amber) / hallucinated (red)
   (`src/lib/verify.ts`).
6. Ask **follow-ups** in the chat thread — every question re-sends the engine facts with a grounding
   reminder, each answer gets its own badge, and a hallucinated reply triggers one automatic correction
   retry. History is trimmed (grounding + first explanation + last 3 turns) to bound token use.
