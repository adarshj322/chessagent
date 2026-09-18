"""Tests that run WITHOUT a Stockfish binary (prompt + verify + tactics + API validation)."""

from fastapi.testclient import TestClient

from .app import app
from .prompt import build_system_prompt, build_user_prompt
from .tactics import analyze_move, build_why
from .verify import extract_san_tokens, verify_explanation

client = TestClient(app)

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE_IN_1 = "7k/5Q2/6p1/6p1/6p1/6p1/5p1P/6K1 w - - 0 1"  # white in check; Qxf2 legal reply
SCHOLARS = "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"  # Qxf7#


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "engine_available" in body
    assert "version" in body


def test_analyze_rejects_bad_fen():
    r = client.post("/api/analyze", json={"fen": "not-a-fen", "depth": 10, "multipv": 1})
    assert r.status_code in (400, 500)
    assert "detail" in r.json()


def test_analyze_validates_depth_bounds():
    r = client.post("/api/analyze", json={"fen": STARTPOS, "depth": 99, "multipv": 1})
    # Pydantic validation fails before engine runs
    assert r.status_code == 422


def test_prompt_contains_grounding():
    sys = build_system_prompt(1200)
    assert "Only discuss moves" in sys
    user = build_user_prompt(
        STARTPOS,
        [{"san": "e4", "uci": "e2e4", "eval_cp": 30, "mate": None}],
        depth=22,
        rating=1200,
        eval_cp=30,
    )
    assert "ENGINE_PVS" in user and "e4" in user


def test_prompt_includes_verified_facts():
    fake_why = {
        "verdict": "e4 keeps a slight edge (+0.30).",
        "why": [{"kind": "positional", "text": "e4 occupies the center."}],
        "threats": ["Best reply is e5."],
        "alternatives": [{"san": "d4", "why": "slightly worse"}],
    }
    user = build_user_prompt(
        STARTPOS,
        [{"san": "e4", "uci": "e2e4", "eval_cp": 30, "mate": None, "pv_san": ["e4", "e5"]}],
        depth=22,
        rating=800,
        eval_cp=30,
        why=fake_why,
    )
    assert "VERIFIED_FACTS" in user and "e4 occupies the center" in user


def test_extract_san_tokens():
    toks = extract_san_tokens("Play Nf3, not Qxh7+? O-O is fine.")
    assert "Nf3" in toks and "Qxh7+" in toks and "O-O" in toks


def test_verify_flags_hallucinated_move():
    res = verify_explanation("Play Nf3 and then Qz9 wins.", STARTPOS, ["Nf3"])
    assert "Nf3" in res["verified"]
    # Qz9 is not a SAN token shape, so nothing unverified here; use illegal-but-shaped move:
    res2 = verify_explanation("Play Nf3 and Qh8 wins.", STARTPOS, ["Nf3"])
    assert "Nf3" in res2["verified"]
    assert "Qh8" in res2["unverified"]  # shaped like SAN but illegal in startpos + not in PVs


def test_verify_three_tiers():
    # e4 is the engine move; d4 is legal but not in PVs; Qh8 is hallucinated.
    res = verify_explanation("Play e4 not d4 and never Qh8.", STARTPOS, ["e4"])
    assert "e4" in res["engine_moves"]
    assert "d4" in res["legal_other"]
    assert "Qh8" in res["hallucinated"]
    assert res["unverified"] == res["hallucinated"]


def test_verify_mate_position_legal():
    res = verify_explanation("Qxf8# wins.", MATE_IN_1, ["Qxf8#"])
    assert res["unverified"] == []


def test_verify_counts_pv_continuation_as_engine():
    res = verify_explanation(
        "After e4 play e5 then Nf3.",
        STARTPOS,
        ["e4"],
        pv_sequences=[["e4", "e5", "Nf3"]],
    )
    assert "e5" in res["engine_moves"] and "Nf3" in res["engine_moves"]


def test_tactics_mate_detection():
    m = analyze_move(SCHOLARS, "h5f7")
    assert m["san"] == "Qxf7#"
    assert m["is_mate"] is True and m["is_capture"] is True


def test_build_why_mate_verdict():
    fake = {
        "best_move_uci": "h5f7",
        "best_move_san": "Qxf7#",
        "eval_cp": None,
        "mate": 1,
        "pv_lines": [
            {"san": "Qxf7#", "uci": "h5f7", "eval_cp": None, "mate": 1,
             "eval_str": "M1", "pv_san": ["Qxf7#"], "eval_loss_cp": 0}
        ],
    }
    why = build_why(SCHOLARS, fake)
    assert "mates on the spot" in why["verdict"]
    assert any(b["kind"] == "mate" for b in why["why"])
    # mate positions stay quiet: no fork/own-hanging noise
    assert all(b["kind"] in ("mate", "material") for b in why["why"])


def test_build_why_startpos_center():
    fake = {
        "best_move_uci": "e2e4",
        "best_move_san": "e4",
        "eval_cp": 30,
        "mate": None,
        "pv_lines": [
            {"san": "e4", "uci": "e2e4", "eval_cp": 30, "mate": None,
             "eval_str": "+0.30", "pv_san": ["e4", "e5", "Nf3"], "eval_loss_cp": 0},
            {"san": "d4", "uci": "d2d4", "eval_cp": 10, "mate": None,
             "eval_str": "+0.10", "pv_san": ["d4"], "eval_loss_cp": 20},
        ],
    }
    why = build_why(STARTPOS, fake)
    assert why["eval_str"] == "+0.30"
    assert "d4" in why["alternatives"][0]["san"]
    assert "0.20" in why["alternatives"][0]["why"]
