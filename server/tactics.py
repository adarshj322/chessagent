"""Deterministic, 100%-accurate move explanation layer.

The LLM is a good *translator* but a bad *source of truth*: it hallucinates
moves and tactics. This module is the source of truth. Everything it returns
is computed from the board + Stockfish numbers with python-chess, so every
bullet is verifiable and never invented:

* what the move *does* (check / mate / capture / promotion / castle / ...)
* material swing in pawns (exact piece values)
* tactical motifs detected on the resulting board (hanging pieces, pins,
  forks/double attacks, double check / discovered check)
* what the opponent's best reply is (taken from the engine PV, not guessed)
* why each alternative is worse (exact eval loss in pawns)

The frontend renders this panel *without any API key*. The LLM prompt then
receives these facts and is only allowed to rephrase them for the student's
rating level.
"""

from __future__ import annotations

import chess

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
CENTER = {chess.E4, chess.D4, chess.E5, chess.D5}


def material_balance(board: chess.Board) -> float:
    """White-minus-Black material in pawns."""
    total = 0
    for sq, piece in board.piece_map().items():
        v = PIECE_VALUES[piece.piece_type]
        total += v if piece.color == chess.WHITE else -v
    return float(total)


def classify_eval_loss(loss_cp: int | None, mate_involved: bool = False) -> str:
    if mate_involved:
        return "loses the forced mate"
    if loss_cp is None:
        return "worse"
    if loss_cp < 10:
        return "equal-best"
    if loss_cp < 35:
        return "slightly worse"
    if loss_cp < 80:
        return "worse"
    if loss_cp < 160:
        return "much worse (inaccuracy)"
    if loss_cp < 320:
        return "mistake"
    return "blunder"


def eval_category(eval_cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return "forced mate" if mate > 0 else "getting mated"
    if eval_cp is None:
        return "unclear"
    a = abs(eval_cp)
    if a < 30:
        return "equal"
    if a < 80:
        return "slight edge"
    if a < 180:
        return "clear advantage"
    return "decisive advantage"


def hanging_pieces(board: chess.Board, victim_color: chess.Color) -> list[dict]:
    """Opponent pieces attacked by the side to move's enemy and undefended.

    Conservative definition: attacked at least once by the other side and
    defended zero times. Reports square + piece names; callers cap the list.
    """
    attacker = not victim_color
    out: list[dict] = []
    for sq, piece in board.piece_map().items():
        if piece.color != victim_color:
            continue
        if board.is_attacked_by(attacker, sq) and not board.is_attacked_by(victim_color, sq):
            out.append({"square": chess.square_name(sq), "piece": PIECE_NAMES[piece.piece_type]})
    return out


def pinned_pieces(board: chess.Board, victim_color: chess.Color) -> list[dict]:
    out: list[dict] = []
    for sq, piece in board.piece_map().items():
        if piece.color != victim_color:
            continue
        try:
            if board.is_pinned(victim_color, sq):
                out.append({"square": chess.square_name(sq), "piece": PIECE_NAMES[piece.piece_type]})
        except ValueError:
            continue
    return out


def _attacks_by(board: chess.Board, from_sq: int, color: chess.Color) -> set[int]:
    return set(board.attacks(from_sq))


def detect_fork(board_after: chess.Board, dest_sq: int, mover: chess.Color) -> list[dict]:
    """Does the moved piece now attack >= 2 valuable enemy units (incl. king)?"""
    victim = not mover
    attacked = _attacks_by(board_after, dest_sq, mover)
    targets: list[dict] = []
    for sq in attacked:
        p = board_after.piece_at(sq)
        if p is not None and p.color == victim and p.piece_type in (
            chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING, chess.PAWN,
        ):
            # Only count meaningful targets: pieces, or pawns if another piece is also hit.
            targets.append({"square": chess.square_name(sq), "piece": PIECE_NAMES[p.piece_type]})
    valuable = [t for t in targets if t["piece"] != "pawn"]
    if len(valuable) >= 2 or (len(valuable) >= 1 and any(t["piece"] == "king" for t in targets)):
        return targets
    if len(targets) >= 2 and len(valuable) >= 1:
        return targets
    return []


def analyze_move(fen: str, best_uci: str) -> dict:
    """Pure board facts about a single move. Raises ValueError on bad input."""
    board = chess.Board(fen)
    try:
        move = chess.Move.from_uci(best_uci)
    except ValueError as exc:
        raise ValueError(f"Bad UCI '{best_uci}': {exc}") from exc
    if move not in board.legal_moves:
        raise ValueError(f"Illegal move {best_uci} for this position")

    mover = board.turn
    victim = not mover
    piece = board.piece_at(move.from_square)
    assert piece is not None
    captured = board.piece_at(move.to_square)
    is_en_passant = board.is_en_passant(move)
    if is_en_passant:
        captured_name = "pawn"
    elif captured is not None:
        captured_name = PIECE_NAMES[captured.piece_type]
    else:
        captured_name = None

    is_capture = board.is_capture(move)
    is_castle = board.is_castling(move)
    is_promotion = move.promotion is not None
    gives_check_before_push = board.gives_check(move)

    san = board.san(move)
    bal_before = material_balance(board)
    board_after = board.copy(stack=False)
    board_after.push(move)
    bal_after = material_balance(board_after)
    swing_white = bal_after - bal_before
    swing_mover = swing_white if mover == chess.WHITE else -swing_white
    swing_mover = swing_mover + 0.0 if swing_mover != 0 else 0.0  # normalize -0.0

    is_check = board_after.is_check()
    is_mate = board_after.is_checkmate()
    is_stalemate = board_after.is_stalemate()

    opp_king = board_after.king(victim)
    king_attackers = board_after.attackers(mover, opp_king) if opp_king is not None else set()
    check_kind = None
    if is_check and opp_king is not None:
        moved_gives = move.to_square in king_attackers or dest_attacks_king(board_after, move.to_square, mover, opp_king)
        if len(king_attackers) >= 2:
            check_kind = "double check"
        elif not moved_gives and gives_check_before_push:
            check_kind = "discovered check"
        elif moved_gives and gives_check_before_push and len(king_attackers) == 1:
            # direct check (could also uncover a line — call it direct unless double)
            check_kind = "direct check"
        else:
            check_kind = "check"

    hanging = hanging_pieces(board_after, victim)[:4]
    # Pieces of the mover that are hanging AFTER the move (risks / sacrifices).
    own_hanging = hanging_pieces(board_after, mover)[:4]
    pins = pinned_pieces(board_after, victim)[:4]
    fork_targets = detect_fork(board_after, move.to_square, mover)

    dest_name = chess.square_name(move.to_square)
    origin_name = chess.square_name(move.from_square)
    return {
        "san": san,
        "uci": move.uci(),
        "piece": PIECE_NAMES[piece.piece_type],
        "from": origin_name,
        "to": dest_name,
        "is_capture": is_capture,
        "captured": captured_name,
        "is_en_passant": is_en_passant,
        "is_castling": is_castle,
        "is_promotion": is_promotion,
        "promotion_piece": PIECE_NAMES[move.promotion] if move.promotion else None,
        "is_check": is_check,
        "check_kind": check_kind,
        "is_mate": is_mate,
        "is_stalemate": is_stalemate,
        "material_swing": round(swing_mover, 1),
        "to_center": move.to_square in CENTER,
        "hanging_enemy": hanging,
        "own_hanging": own_hanging,
        "pins_enemy": pins,
        "fork_targets": fork_targets,
        "mover": "white" if mover == chess.WHITE else "black",
    }


def dest_attacks_king(board_after: chess.Board, dest: int, mover: chess.Color, king_sq: int) -> bool:
    return king_sq in board_after.attacks(dest)


def build_why(fen: str, analysis: dict) -> dict:
    """Combine board facts + engine PVs into learner-ready deterministic output.

    ``analysis`` is the payload from engine.analyze_position (or an equivalent
    dict with pv_lines/best_move_uci/eval_cp/mate). Never calls the engine.
    """
    best_uci: str = analysis["best_move_uci"]
    facts = analyze_move(fen, best_uci)
    pv_lines: list[dict] = analysis.get("pv_lines", [])
    best = pv_lines[0] if pv_lines else {}
    eval_cp = analysis.get("eval_cp")
    mate = analysis.get("mate")
    mover_name = "White" if facts["mover"] == "white" else "Black"

    bullets: list[dict] = []

    def add(kind: str, text: str) -> None:
        bullets.append({"kind": kind, "text": text})

    # 1 — terminal / forcing lines first (most important for learning).
    if facts["is_mate"]:
        add("mate", f"{facts['san']} is checkmate — the game ends immediately.")
    elif mate is not None and mate > 0:
        add("mate", f"{facts['san']} forces mate in {mate}. Follow the main line: {' '.join(best.get('pv_san', [facts['san']])[:6])}.")
    elif mate is not None and mate < 0:
        add("danger", f"Even the best move only delays mate in {abs(mate)} — the position is lost; {facts['san']} resists longest.")

    if facts["is_check"] and not facts["is_mate"]:
        add("check", f"{facts['san']} gives {facts['check_kind'] or 'check'}, forcing {mover_name.lower() == 'white' and 'Black' or 'White'} to respond to the check first.")
    if facts["is_stalemate"]:
        add("danger", f"Careful: {facts['san']} stalemates the opponent — no legal moves but not in check, so the game is drawn.")

    # 2 — material truth.
    if facts["is_capture"]:
        if facts["material_swing"] > 0:
            add("material", f"{facts['san']} captures the {facts['captured']} on {facts['to']} — a gain of about {facts['material_swing']:g} pawn(s) with no recapture.")
        elif facts["material_swing"] == 0:
            add("material", f"{facts['san']} captures on {facts['to']} but the opponent recaptures — an equal trade that improves the position rather than winning material.")
        else:
            add("material", f"{facts['san']} is a sacrifice: it gives up about {abs(facts['material_swing']):g} pawn(s) of material for attack/positional compensation (engine still rates it best at {best.get('eval_str', '?')}).")
    if facts["is_promotion"]:
        add("material", f"{facts['san']} promotes to a {facts['promotion_piece']} — the new piece decides the game.")
    if facts["is_castling"]:
        add("safety", f"{facts['san']} castles: the king reaches safety and the rook joins the center in one move.")
    if facts["is_en_passant"]:
        add("tactic", f"{facts['san']} is an en-passant capture — it removes the pawn that just double-pushed.")

    # 3 — tactics created by the move (skipped on mate: game is over, the
    # extra detections are noise for learners).
    if not facts["is_mate"]:
        for h in facts["hanging_enemy"]:
            add("tactic", f"After {facts['san']}, the enemy {h['piece']} on {h['square']} is hanging (attacked and undefended).")
        for p in facts["pins_enemy"]:
            add("tactic", f"After {facts['san']}, the enemy {p['piece']} on {p['square']} is pinned and cannot move without exposing its king.")
        if facts["fork_targets"]:
            names = ", ".join(f"{t['piece']} on {t['square']}" for t in facts["fork_targets"][:3])
            add("tactic", f"{facts['san']} is a double attack: the {facts['piece']} on {facts['to']} hits {names} at once.")
        for h in facts["own_hanging"]:
            add("danger", f"Note: after {facts['san']} your own {h['piece']} on {h['square']} is en prise — it only works because of the concrete follow-up.")

    # 4 — positional truth.
    if facts["to_center"] and facts["piece"] in ("pawn", "knight"):
        add("positional", f"{facts['san']} occupies the center ({facts['to']}), controlling key squares and freeing pieces.")
    if not bullets:
        cat = eval_category(eval_cp, mate)
        add("positional", f"{facts['san']} is the engine's top choice ({best.get('eval_str', '?')}, {cat}). It improves coordination with no tactics attached — the quiet best move.")

    # Verdict line (1 sentence, always grounded in numbers).
    if facts["is_mate"]:
        verdict = f"{facts['san']} mates on the spot."
    elif mate is not None and mate > 0:
        verdict = f"{facts['san']} forces mate in {mate} — every defence falls short."
    elif facts["is_capture"] and facts["material_swing"] > 0:
        verdict = f"{facts['san']} wins about {facts['material_swing']:g} pawn(s) ({best.get('eval_str', '?')})."
    else:
        cat = eval_category(eval_cp, mate)
        verdict = f"{facts['san']} keeps a {cat} ({best.get('eval_str', '?')})."

    # Threats: what happens next (from the PV, never invented).
    threats: list[str] = []
    pv_san: list[str] = best.get("pv_san", [facts["san"]])
    if len(pv_san) >= 2:
        threats.append(f"Best reply is {pv_san[1]}; then the idea continues { ' '.join(pv_san[:min(4, len(pv_san))]) }.")
    elif facts["is_check"] and not facts["is_mate"]:
        threats.append(f"{mover_name} threatens to press the attack while the king is exposed.")
    if facts["hanging_enemy"]:
        h = facts["hanging_enemy"][0]
        threats.append(f"Immediate threat: win the {h['piece']} on {h['square']} if it is not defended.")
    if mate is not None and mate > 0 and len(pv_san) >= 3:
        threats.append(f"Mating net tightens with {' '.join(pv_san[1:4])} — every king move has been calculated.")

    # Alternatives: exact eval loss (numbers, not adjectives alone).
    alternatives: list[dict] = []
    for line in pv_lines[1:4]:
        loss = line.get("eval_loss_cp")
        mate_flag = line.get("mate") is not None or mate is not None
        if loss is None and not mate_flag:
            why = "worse by an unclear amount"
        elif mate_flag and line.get("mate") != mate:
            why = "lets the mate slip" if (mate or 0) > 0 else "defends worse"
        else:
            pawns = (loss or 0) / 100
            why = f"{classify_eval_loss(loss, False)} — gives up ~{pawns:.2f} pawns vs best ({line.get('eval_str', '?')} vs {best.get('eval_str', '?')})"
        alternatives.append({"san": line.get("san"), "uci": line.get("uci"), "eval_str": line.get("eval_str"), "why": why})

    return {
        "verdict": verdict,
        "facts": facts,
        "why": bullets,
        "threats": threats,
        "alternatives": alternatives,
        "eval_str": best.get("eval_str", "?"),
        "eval_category": eval_category(eval_cp, mate),
        "pv_san": pv_san,
    }
