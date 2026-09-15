# Web — Stockfish Move Analyzer (Vite + React + TS)

Board + engine panel + OpenRouter BYOK explanation. Your API key stays in
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
`VITE_API_URL=https://your-api-host`.

## Flow

1. Move pieces / paste FEN → **Analyze** → `POST /api/analyze`.
2. Enter OpenRouter key → **Validate + load models** → pick any model.
3. **Explain with LLM** → streams markdown; moves not in engine PVs get an
   "unverified" badge (`src/lib/verify.ts`).
