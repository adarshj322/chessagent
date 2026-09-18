"""Anti-hallucination helper: 3-tier verification of SANs mentioned by the LLM.

Tiers
----
* ``engine_moves`` — the move appears in a Stockfish PV (first move or deeper
  continuation). Citing these is always safe.
* ``legal_other`` — legal in the position but NOT recommended by the engine.
  Usually fine as a mentioned alternative, flagged amber.
* ``hallucinated`` — shaped like a SAN token but neither in the PVs nor legal
  (or not even a legal chess token shape that resolves). Treat with caution.

Backward compatibility: ``verified`` = engine_moves + legal_other and
``unverified`` = hallucinated, matching the original 2-tier API.
"""

from __future__ import annotations

import re

import chess

# Matches tokens like Nf3, exd5, O-O, O-O-O, Qxh7+, Rd8#, Bb5, a8=Q (with optional +/#).
# Note: no trailing \b — it would drop check/mate suffixes (+/#) since they are non-word chars.
SAN_TOKEN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?")


def extract_san_tokens(text: str) -> list[str]:
    return SAN_TOKEN.findall(text or "")


def _norm(san: str) -> str:
    return san.strip().rstrip("+#").replace("0-0", "O-O").replace("0-0-0", "O-O-O")


def verify_explanation(
    text: str,
    fen: str,
    pv_sans: list[str],
    pv_sequences: list[list[str]] | None = None,
) -> dict:
    """Return tiered verification for an explanation.

    Args:
        text: free-form LLM explanation.
        fen: position the explanation is about.
        pv_sans: first moves of each engine PV.
        pv_sequences: full PV SAN sequences (deeper continuations also count
            as engine moves so the model isn't punished for citing the line).
    """
    tokens = extract_san_tokens(text)

    pv_set = {_norm(s) for s in (pv_sans or [])}
    if pv_sequences:
        for seq in pv_sequences:
            for s in seq or []:
                pv_set.add(_norm(s))

    try:
        board = chess.Board(fen)
        legal = {_norm(board.san(m)) for m in board.legal_moves}
    except ValueError:
        legal = set()

    engine_moves: list[str] = []
    legal_other: list[str] = []
    hallucinated: list[str] = []
    for tok in tokens:
        base = _norm(tok)
        if base in pv_set:
            engine_moves.append(tok)
        elif base in legal:
            legal_other.append(tok)
        else:
            hallucinated.append(tok)

    verified = [*engine_moves, *legal_other]
    return {
        "tokens": tokens,
        "engine_moves": engine_moves,
        "legal_other": legal_other,
        "hallucinated": hallucinated,
        # legacy 2-tier keys
        "verified": verified,
        "unverified": hallucinated,
    }
