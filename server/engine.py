"""Stockfish UCI wrapper with concurrency limit + in-memory cache.

The API key for OpenRouter never touches this service (local-only BYOK).
This service only runs engine analysis.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections import OrderedDict

import chess
import chess.engine

STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "stockfish")
MAX_CONCURRENT = int(os.getenv("ENGINE_MAX_CONCURRENT", "2"))
ENGINE_TIMEOUT = float(os.getenv("ENGINE_TIMEOUT_S", "30"))
CACHE_SIZE = int(os.getenv("ENGINE_CACHE_SIZE", "256"))

_sem = asyncio.Semaphore(MAX_CONCURRENT)
_cache: OrderedDict[str, dict] = OrderedDict()


def cache_key(fen: str, depth: int, multipv: int) -> str:
    raw = f"{fen}|{depth}|{multipv}".encode()
    return hashlib.sha256(raw).hexdigest()


def cache_get(key: str) -> dict | None:
    item = _cache.get(key)
    if item is None:
        return None
    # LRU bump
    _cache.move_to_end(key)
    return item


def cache_put(key: str, value: dict) -> None:
    _cache[key] = value
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)


def engine_available() -> bool:
    import shutil

    return shutil.which(STOCKFISH_PATH) is not None


async def analyze_position(fen: str, depth: int = 22, multipv: int = 3) -> dict:
    """Run Stockfish on a FEN. Raises ValueError on bad FEN, RuntimeError on engine issues."""
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"Invalid FEN: {exc}") from exc
    if board.is_game_over():
        # Still allow analysis; engine handles mate/stalemate positions.
        pass

    depth = max(1, min(28, depth))
    multipv = max(1, min(5, multipv))
    key = cache_key(fen, depth, multipv)
    cached = cache_get(key)
    if cached is not None:
        return {**cached, "cached": True}

    if not engine_available():
        raise RuntimeError(
            f"Stockfish binary not found at '{STOCKFISH_PATH}'. "
            "Install stockfish (apt/brew) or set STOCKFISH_PATH."
        )

    async with _sem:
        try:
            transport, engine = await chess.engine.popen_uci(STOCKFISH_PATH)
        except Exception as exc:
            raise RuntimeError(f"Could not start Stockfish: {exc}") from exc
        try:
            start = time.monotonic()
            result = await asyncio.wait_for(
                engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv),
                timeout=ENGINE_TIMEOUT,
            )
            elapsed = time.monotonic() - start
        except asyncio.TimeoutError as exc:
            raise RuntimeError(f"Engine timed out after {ENGINE_TIMEOUT}s") from exc
        finally:
            try:
                await engine.quit()
            except Exception:
                pass

    # python-chess returns a list when multipv > 1, else a single dict
    infos = result if isinstance(result, list) else [result]
    pv_lines: list[dict] = []
    for info in infos:
        pv = info.get("pv", [])
        if not pv:
            continue
        uci = pv[0].uci()
        san = board.san(pv[0])
        score = info.get("score")
        eval_cp = mate = None
        if score is not None:
            # score is relative to side to move
            pov = score.pov(board.turn)
            mate = pov.mate()
            eval_cp = None if mate is not None else pov.score()
        pv_lines.append({"uci": uci, "san": san, "eval_cp": eval_cp, "mate": mate})

    if not pv_lines:
        raise RuntimeError("Engine returned no principal variation")

    best = pv_lines[0]
    payload = {
        "fen": fen,
        "best_move_uci": best["uci"],
        "best_move_san": best["san"],
        "eval_cp": best["eval_cp"],
        "mate": best["mate"],
        "depth_reached": infos[0].get("depth", depth),
        "pv_lines": pv_lines,
        "nodes": infos[0].get("nodes"),
        "nps": infos[0].get("nps"),
        "engine": "stockfish",
        "cached": False,
        "elapsed_s": round(elapsed, 2),
    }
    cache_put(key, {k: v for k, v in payload.items() if k != "cached"})
    return payload


def clear_cache() -> None:
    _cache.clear()
