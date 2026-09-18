"""Stockfish UCI wrapper: persistent engine pool + TTL LRU cache.

Design notes
------------
* A small pool of long-lived UCI processes is far cheaper than spawning one
  process per request (old behaviour) and is required for production latency.
* Each pooled engine is guarded by its own lock; callers acquire any free
  engine. If the pool cannot start (no binary), requests fail with a clear
  503-style RuntimeError instead of hanging.
* Analysis payloads include the FULL principal variation (SAN + UCI, up to
  ``PV_MAX_PLIES``) plus normalized evals — this is what lets the frontend
  and the LLM stay grounded instead of guessing.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import time
from collections import OrderedDict
from dataclasses import dataclass

import chess
import chess.engine

from .settings import settings

log = logging.getLogger("stockfish-api.engine")

PV_MAX_PLIES = 8

_sem = asyncio.Semaphore(settings.engine_max_concurrent)
_cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------- cache

def cache_key(fen: str, depth: int, multipv: int) -> str:
    raw = f"{fen}|{depth}|{multipv}".encode()
    return hashlib.sha256(raw).hexdigest()


async def cache_get(key: str) -> dict | None:
    async with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        ts, value = hit
        if time.monotonic() - ts > settings.engine_cache_ttl_s:
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return value


async def cache_put(key: str, value: dict) -> None:
    async with _cache_lock:
        _cache[key] = (time.monotonic(), value)
        _cache.move_to_end(key)
        while len(_cache) > settings.engine_cache_size:
            _cache.popitem(last=False)


def clear_cache() -> None:
    _cache.clear()


def cache_stats() -> dict:
    return {"entries": len(_cache), "max": settings.engine_cache_size}


# ---------------------------------------------------------------- helpers

def engine_available() -> bool:
    return shutil.which(settings.stockfish_path) is not None


def cp_to_win_pct(cp: int | None) -> float | None:
    """Lichess-style win probability (percent) for the side to move."""
    if cp is None:
        return None
    import math

    # 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1)
    win = 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)
    return round(max(0.0, min(100.0, win)), 1)


def format_eval(eval_cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"M{mate}" if mate > 0 else f"-M{abs(mate)}"
    if eval_cp is None:
        return "?"
    pawns = eval_cp / 100
    return f"{'+' if pawns >= 0 else ''}{pawns:.2f}"


def _validate_fen(fen: str) -> chess.Board:
    fen = (fen or "").strip()
    if not fen or len(fen) > 200:
        raise ValueError("Invalid FEN: empty or too long")
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise ValueError(f"Invalid FEN: {exc}") from exc
    # python-chess accepts some illegal positions; hard-reject the common ones.
    if not board.is_valid():
        raise ValueError("Invalid FEN: illegal position (king count / pawns / checks)")
    return board


def _pv_to_sans(board: chess.Board, pv: list[chess.Move], limit: int = PV_MAX_PLIES) -> tuple[list[str], list[str]]:
    """Replay a PV on a copy of the board; stop at first illegal move."""
    b = board.copy(stack=False)
    sans: list[str] = []
    ucis: list[str] = []
    for mv in pv[:limit]:
        try:
            sans.append(b.san(mv))
            ucis.append(mv.uci())
            b.push(mv)
        except ValueError:
            break
    return sans, ucis


# ---------------------------------------------------------------- pool

@dataclass
class _PooledEngine:
    transport: object
    engine: chess.engine.UciProtocol
    lock: asyncio.Lock


_pool: list[_PooledEngine] = []
_pool_init_lock = asyncio.Lock()
_pool_shutdown = False


async def _spawn_engine() -> _PooledEngine:
    try:
        transport, eng = await chess.engine.popen_uci(settings.stockfish_path)
    except Exception as exc:
        raise RuntimeError(
            f"Stockfish binary not found at '{settings.stockfish_path}'. "
            "Install stockfish (apt/brew) or set STOCKFISH_PATH."
        ) from exc
    try:
        await eng.configure({"Threads": settings.engine_threads, "Hash": settings.engine_hash_mb})
    except Exception as exc:  # non-fatal: older binaries may reject options
        log.warning("engine configure failed: %s", exc)
    return _PooledEngine(transport=transport, engine=eng, lock=asyncio.Lock())


async def warm_pool() -> int:
    """Start up to ENGINE_MAX_CONCURRENT engines. Returns number started."""
    global _pool
    if not engine_available():
        log.warning("stockfish binary not found at %s; pool not warmed", settings.stockfish_path)
        return 0
    async with _pool_init_lock:
        while len(_pool) < settings.engine_max_concurrent:
            try:
                _pool.append(await _spawn_engine())
            except RuntimeError as exc:
                log.warning("pool warm failed: %s", exc)
                break
    return len(_pool)


async def close_pool() -> None:
    global _pool, _pool_shutdown
    _pool_shutdown = True
    for item in _pool:
        try:
            await item.engine.quit()
        except Exception:
            pass
    _pool = []


async def _acquire() -> _PooledEngine:
    if not engine_available():
        raise RuntimeError(
            f"Stockfish binary not found at '{settings.stockfish_path}'. "
            "Install stockfish (apt/brew) or set STOCKFISH_PATH."
        )
    async with _pool_init_lock:
        for item in _pool:
            if not item.lock.locked():
                await item.lock.acquire()
                return item
        if len(_pool) < settings.engine_max_concurrent and not _pool_shutdown:
            try:
                item = await _spawn_engine()
                _pool.append(item)
                await item.lock.acquire()
                return item
            except RuntimeError:
                pass
    # Pool full — wait for any engine to free up.
    while True:
        async with _pool_init_lock:
            snapshot = list(_pool)
        if not snapshot:
            raise RuntimeError("Engine pool unavailable")
        # Wait on the first unlocked-or-soon-free engine.
        for item in snapshot:
            if not item.lock.locked():
                await item.lock.acquire()
                return item
        await asyncio.sleep(0.02)


def _release(item: _PooledEngine) -> None:
    try:
        if item.lock.locked():
            item.lock.release()
    except RuntimeError:
        pass


# ---------------------------------------------------------------- main entry

async def analyze_position(fen: str, depth: int = 22, multipv: int = 3) -> dict:
    """Run Stockfish on a FEN. Raises ValueError (bad input) / RuntimeError (engine)."""
    board = _validate_fen(fen)

    depth = max(1, min(settings.max_depth, depth))
    multipv = max(1, min(settings.max_multipv, multipv))
    key = cache_key(board.fen(), depth, multipv)
    cached = await cache_get(key)
    if cached is not None:
        return {**cached, "cached": True}

    # Game-over positions: still return engine data when possible, but the
    # deterministic layer marks the result as terminal.
    terminal = board.is_game_over()
    terminal_result = board.result() if terminal else None

    async with _sem:
        item = await _acquire()
        try:
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    item.engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv),
                    timeout=settings.engine_timeout_s,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(f"Engine timed out after {settings.engine_timeout_s}s") from exc
            elapsed = time.monotonic() - start
        finally:
            _release(item)

    infos = result if isinstance(result, list) else [result]
    # MultiPV infos may arrive unordered — sort best-first by score POV side-to-move.
    def _sort_key(info: dict) -> float:
        sc = info.get("score")
        if sc is None:
            return float("-inf")
        pov = sc.pov(board.turn)
        m = pov.mate()
        if m is not None:
            return 100000 + m if m > 0 else -100000 - m
        s = pov.score()
        return float(s if s is not None else "-inf")

    infos = sorted(infos, key=_sort_key, reverse=True)

    pv_lines: list[dict] = []
    for info in infos:
        pv = info.get("pv", [])
        if not pv:
            continue
        sans, ucis = _pv_to_sans(board, list(pv))
        if not sans:
            continue
        score = info.get("score")
        eval_cp = mate = None
        if score is not None:
            pov = score.pov(board.turn)
            mate = pov.mate()
            eval_cp = None if mate is not None else pov.score()
        pv_lines.append(
            {
                "uci": ucis[0],
                "san": sans[0],
                "eval_cp": eval_cp,
                "mate": mate,
                "win_pct": None if mate is not None else cp_to_win_pct(eval_cp),
                "eval_str": format_eval(eval_cp, mate),
                "pv_san": sans,
                "pv_uci": ucis,
                "depth": info.get("depth", depth),
            }
        )

    if not pv_lines:
        raise RuntimeError("Engine returned no principal variation")

    # Eval loss of each alternative vs best (in cp; mate differences flagged separately).
    best = pv_lines[0]
    for i, line in enumerate(pv_lines):
        if i == 0:
            line["eval_loss_cp"] = 0
            continue
        if line["mate"] is not None or best["mate"] is not None:
            line["eval_loss_cp"] = None
        elif line["eval_cp"] is not None and best["eval_cp"] is not None:
            line["eval_loss_cp"] = max(0, best["eval_cp"] - line["eval_cp"])
        else:
            line["eval_loss_cp"] = None

    payload = {
        "fen": board.fen(),
        "best_move_uci": best["uci"],
        "best_move_san": best["san"],
        "best_pv_san": best["pv_san"],
        "best_pv_uci": best["pv_uci"],
        "eval_cp": best["eval_cp"],
        "mate": best["mate"],
        "win_pct": best["win_pct"],
        "eval_str": best["eval_str"],
        "depth_reached": infos[0].get("depth", depth),
        "depth_requested": depth,
        "pv_lines": pv_lines,
        "nodes": infos[0].get("nodes"),
        "nps": infos[0].get("nps"),
        "is_terminal": terminal,
        "terminal_result": terminal_result,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "engine": "stockfish",
        "cached": False,
        "elapsed_s": round(elapsed, 2),
    }
    await cache_put(key, {k: v for k, v in payload.items() if k != "cached"})
    return payload
