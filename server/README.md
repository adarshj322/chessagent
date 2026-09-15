# Stockfish server — single-position analysis API

No LLM keys here. The browser calls OpenRouter directly (BYOK).

## Setup (Python 3.11 or 3.12 recommended)

Pydantic/FastAPI wheels may not exist yet for Python 3.14, so prefer 3.11/3.12.

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

## Run

```bash
uvicorn server.app:app --reload --port 8000
# health: GET http://localhost:8000/api/health
```

## API

`POST /api/analyze` — `{fen, depth (1-28, default 22), multipv (1-5, default 3)}`

Returns best move, eval (cp or mate), depth reached, PV lines, nodes/nps.
Responses are cached in-memory by `fen+depth+multipv` (LRU 256).

Errors: `400` bad FEN, `503` engine missing/timeout, `500` engine error.

## Tests

`test_app.py` covers prompt grounding + SAN verification + API validation.
The prompt/verify subset runs without a Stockfish binary or FastAPI:

```bash
python3 -c "import sys; sys.path.insert(0,'.'); from server.verify import verify_explanation; print(verify_explanation('Nf3 wins', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', ['Nf3']))"
```

Full suite needs FastAPI + pytest: `python -m pytest server/test_app.py -v`.
