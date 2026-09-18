"""Grounded prompt builders for OpenRouter explanations.

Kept in the backend for testing/documentation; the frontend (web/src/lib/prompt.ts)
mirrors this logic and calls OpenRouter directly from the browser (BYOK).

Architecture: the deterministic layer (server/tactics.py) is the SOURCE OF
TRUTH. These prompts hand its VERIFIED_FACTS to the LLM with one job: rephrase
them into learner-friendly language for the student's rating. The model must
never invent moves, evals, or tactics — and the 3-tier verifier checks that.
"""

from __future__ import annotations


def build_system_prompt(rating: int = 1200) -> str:
    level = "beginner" if rating < 1000 else "intermediate" if rating < 1600 else "advanced"
    depth_guide = (
        "Use plain words, one idea per sentence, and explain every chess term you use."
        if level == "beginner"
        else "Be concrete: squares, pieces, and exact sequences. Assume basic tactical vocabulary."
        if level == "intermediate"
        else "Be dense and precise: candidate moves, prophylaxis, and engine-line nuances. No hand-holding."
    )
    return (
        "You are a chess coach explaining a Stockfish analysis to a "
        f"{level} player (rating ~{rating}). {depth_guide}\n"
        "You are given VERIFIED_FACTS computed by a chess engine from the real board. "
        "They are always correct. Your job is ONLY to rephrase them clearly.\n"
        "STRICT RULES:\n"
        "1. Only discuss moves that appear in ENGINE_PVS or VERIFIED_FACTS. Never invent variations.\n"
        "2. Never invent evaluations, mate counts, or threats — reuse the numbers given.\n"
        "3. If VERIFIED_FACTS say a move wins material or mates, say exactly that; do not soften it.\n"
        "4. If the position is quiet/positional, say so instead of inventing tactics.\n"
        "5. Keep tactics concrete (squares + pieces), avoid purple prose.\n"
        "Output markdown with exactly these sections:\n"
        "## Verdict (1 line)\n"
        "## Why this move\n"
        "## Threats & ideas\n"
        "## Why not the alternatives"
    )


def _fmt_eval(eval_cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"M{mate}" if mate > 0 else f"-M{abs(mate)}"
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
    why: dict | None = None,
) -> str:
    """Build the grounded user prompt.

    ``pv_lines`` entries may carry full ``pv_san`` sequences (preferred) or
    just ``san``/``uci``. ``why`` is the deterministic build_why() output.
    """
    rows: list[str] = []
    for i, p in enumerate(pv_lines):
        seq = p.get("pv_san") or [p.get("san", "?")]
        seq_str = " ".join(seq[:6])
        loss = p.get("eval_loss_cp")
        loss_str = "" if i == 0 or loss is None else f" eval_loss={loss / 100:.2f}p"
        rows.append(
            f"PV{i + 1}: {seq_str} (first {p.get('san', '?')} {p.get('uci', '?')}) "
            f"eval={_fmt_eval(p.get('eval_cp'), p.get('mate'))}{loss_str}"
        )
    pvs = "\n".join(rows)

    facts_block = ""
    if why:
        why_lines = "\n".join(f"- [{b.get('kind', 'fact')}] {b.get('text', '')}" for b in why.get("why", []))
        threat_lines = "\n".join(f"- {t}" for t in why.get("threats", []))
        alt_lines = "\n".join(
            f"- {a.get('san')}: {a.get('why')}" for a in why.get("alternatives", [])
        )
        facts_block = (
            f"\nVERIFIED_FACTS (always true — rephrase, do not contradict):\n"
            f"Verdict: {why.get('verdict', '')}\n"
            f"Why:\n{why_lines or '- (quiet best move)'}\n"
            f"Threats:\n{threat_lines or '- none forced'}\n"
            f"Alternatives:\n{alt_lines or '- no alternatives given'}\n"
        )
    return (
        f"Position FEN: {fen}\n"
        f"Engine: Stockfish, depth {depth}\n"
        f"Top-line eval (side to move): {_fmt_eval(eval_cp, mate)}\n"
        f"ENGINE_PVS (only moves you may cite):\n{pvs}\n"
        f"{facts_block}"
        f"Student rating: ~{rating}\n"
        "Explain the best move (PV1) vs PV2/PV3, following VERIFIED_FACTS."
    )
