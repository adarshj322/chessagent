"""FastAPI app: single-position Stockfish analysis. No LLM keys here (BYOK)."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import engine
from .schemas import AnalyzeRequest, AnalyzeResponse

app = FastAPI(title="Stockfish Move Analyzer API", version="0.1.0")

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "engine_available": engine.engine_available()}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> dict:
    try:
        return await engine.analyze_position(req.fen, req.depth, req.multipv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        code = 503 if "not found" in msg or "timed out" in msg.lower() else 500
        raise HTTPException(status_code=code, detail=msg) from exc
