"""Grounded prompt builders for OpenRouter explanations.

Kept in the backend for testing/documentation; the frontend (web/src/lib/prompt.ts)
mirrors this logic and calls OpenRouter directly from the browser (BYOK).
"""

from __future__ import annotations


def build_system_prompt(rating: int = 1200) -> str:
    level = "beginner" if rating < 1000 else "intermediate" if rating < 1600 else "advanced"
    return (
        "You are a concise chess coach explaining a Stockfish analysis to a "
        f"{level} player (rating ~{rating}).\n"
        "STRICT RULES:\n"
        "1. Only discuss moves that appear in ENGINE_PVS or are legal replies to them.\n"
        "2. Never invent variations, evaluations, or threats not supported by the engine data.\n"
        "3. If the position is unclear, say so instead of guessing.\n"
        "4. Keep tactics concrete (squares + pieces), avoid purple prose.\n"
        "Output markdown with exactly these sections:\n"
        "## Verdict (1 line)\n"
        "## Why this move\n"
        "## Threats & ideas\n"
        "## Why not the alternatives"
    )


def _fmt_eval(eval_cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"M{ mate}" if mate > 0 else f"-M{abs(mate)}"
    if eval_cp is None:
        return "?"
    pawns = eval_cp / 100
    sign = "+" if pawns >= 0 else ""
    return f"{sign}{pawns:.2f}"


def build_user_prompt(
    fen: str,
    pv_lines: list[dict],
    depth: int,
    rating: int = 1200,
    eval_cp: int | None = None,
    mate: int | None = None,
) -> str:
    pvs = "\n".join(
        f"PV{i + 1}: {p['san']} ({p['uci']}) eval={_fmt_eval(p.get('eval_cp'), p.get('mate'))}"
        for i, p in enumerate(pv_lines)
    )
    return (
        f"Position FEN: {fen}\n"
        f"Engine: Stockfish, depth {depth}\n"
        f"Top-line eval (side to move): {_fmt_eval(eval_cp, mate)}\n"
        f"ENGINE_PVS (only moves you may cite):\n{pvs}\n"
        f"Student rating: ~{rating}\n"
        "Explain the best move (PV1) vs PV2/PV3."
    )
