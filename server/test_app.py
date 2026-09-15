"""Tests that run WITHOUT a Stockfish binary (prompt + verify + API validation)."""

from fastapi.testclient import TestClient

from .app import app
from .prompt import build_system_prompt, build_user_prompt
from .verify import extract_san_tokens, verify_explanation

client = TestClient(app)

STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE_IN_1 = "7k/5Q2/6p1/6p1/6p1/6p1/5p1P/6K1 w - - 0 1"  # Qxf8# / Qg7# ideas


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "engine_available" in r.json()


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


def test_verify_mate_position_legal():
    res = verify_explanation("Qxf8# wins.", MATE_IN_1, ["Qxf8#"])
    assert res["unverified"] == []
