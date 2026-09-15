"""Anti-hallucination helper: verify SANs mentioned by the LLM.

The LLM must only cite engine PV moves. This extracts SAN-looking tokens
from free text and splits them into verified (in engine PV set or legal)
vs unverified.
"""

from __future__ import annotations

import re

import chess

# Matches tokens like Nf3, exd5, O-O, Qxh7+, Rd8#, Bb5, a8=Q (with optional +/#)
# Note: no trailing \b — it would drop check/mate suffixes (+/#) since they are non-word chars.
SAN_TOKEN = re.compile(r"\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?")


def extract_san_tokens(text: str) -> list[str]:
    return SAN_TOKEN.findall(text)


def verify_explanation(text: str, fen: str, pv_sans: list[str]) -> dict:
    """Return {tokens, verified, unverified} for an explanation."""
    tokens = extract_san_tokens(text)
    pv_set = {s.strip().rstrip("+#") for s in pv_sans}

    try:
        board = chess.Board(fen)
        legal = {board.san(m).rstrip("+#") for m in board.legal_moves}
    except ValueError:
        legal = set()

    verified, unverified = [], []
    for tok in tokens:
        base = tok.rstrip("+#")
        if base in pv_set:
            verified.append(tok)
        elif base in legal:
            verified.append(tok)  # legal board move, but not top engine line
        else:
            unverified.append(tok)
    return {"tokens": tokens, "verified": verified, "unverified": unverified}
