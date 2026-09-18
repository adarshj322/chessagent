"""FastAPI app: single-position Stockfish analysis + deterministic why.

No LLM keys here (BYOK): the browser calls OpenRouter directly. This service
only runs the engine and computes verifiable board facts.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from . import engine
from .schemas import AnalyzeRequest, AnalyzeResponse, ErrorResponse, VerifyRequest
from .settings import settings
from .tactics import build_why
from .verify import verify_explanation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("stockfish-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    n = await engine.warm_pool()
    log.info("engine pool warmed: %d/%d", n, settings.engine_max_concurrent)
    yield
    await engine.close_pool()
    log.info("engine pool closed")


app = FastAPI(title="Stockfish Move Analyzer API", version=settings.app_version, lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error rid=%s %s %s", rid, request.method, request.url.path)
            raise
        response.headers["X-Request-Id"] = rid
        response.headers["X-Elapsed-Ms"] = str(int((time.monotonic() - start) * 1000))
        return response


app.add_middleware(RequestIdMiddleware)


# ---------------------------------------------------------------- rate limit
_hits: dict[str, list[float]] = defaultdict(list)


async def _rate_limit(request: Request) -> None:
    limit = settings.rate_limit_per_min
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _hits[ip]
    while window and now - window[0] > 60:
        window.pop(0)
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/min). Slow down.")
    window.append(now)


# ---------------------------------------------------------------- routes

@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "version": settings.app_version,
        "engine_available": engine.engine_available(),
        "cache": engine.cache_stats(),
        "limits": {
            "max_depth": settings.max_depth,
            "max_multipv": settings.max_multipv,
            "rate_per_min": settings.rate_limit_per_min,
        },
    }


@app.post("/api/analyze", response_model=AnalyzeResponse, responses={400: {"model": ErrorResponse}})
async def analyze(req: AnalyzeRequest, request: Request) -> dict:
    await _rate_limit(request)
    try:
        result = await engine.analyze_position(req.fen, req.depth, req.multipv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        lowered = msg.lower()
        code = 503 if ("not found" in msg or "timed out" in lowered or "unavailable" in lowered) else 500
        raise HTTPException(status_code=code, detail=msg) from exc
    # Deterministic why-layer: never allowed to break the engine response.
    try:
        result["explanation"] = build_why(result["fen"], result)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("build_why failed: %s", exc)
        result["explanation"] = None
    return result


@app.post("/api/verify")
async def verify(req: VerifyRequest) -> dict:
    """Server-side 3-tier check for an LLM explanation (no key needed)."""
    if len(req.text) > 20000:
        raise HTTPException(status_code=400, detail="Text too long (max 20000 chars)")
    return verify_explanation(req.text, req.fen, req.pv_sans, req.pv_sequences)


@app.delete("/api/cache")
async def drop_cache() -> dict:
    engine.clear_cache()
    return {"ok": True}
