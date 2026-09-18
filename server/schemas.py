"""Shared Pydantic schemas for the Stockfish analyze API."""

from typing import Optional

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    fen: str = Field(description="FEN string of the position to analyze")
    depth: int = Field(default=22, ge=1, le=28, description="Search depth (capped at 28 for MVP)")
    multipv: int = Field(default=3, ge=1, le=5, description="Number of principal variations")


class PvLine(BaseModel):
    uci: str
    san: str
    eval_cp: Optional[int] = None
    mate: Optional[int] = None
    win_pct: Optional[float] = None
    eval_str: str = "?"
    eval_loss_cp: Optional[int] = None
    pv_san: list[str] = Field(default_factory=list, description="Full PV in SAN (up to 8 plies)")
    pv_uci: list[str] = Field(default_factory=list)
    depth: Optional[int] = None


class WhyBullet(BaseModel):
    kind: str = Field(description="mate|check|material|tactic|safety|positional|danger")
    text: str


class Alternative(BaseModel):
    san: Optional[str] = None
    uci: Optional[str] = None
    eval_str: Optional[str] = None
    why: str


class MoveFacts(BaseModel):
    san: str
    uci: str
    piece: str
    model_config = {"extra": "allow"}  # tactics dict carries many detected fields


class WhyExplanation(BaseModel):
    verdict: str
    why: list[WhyBullet] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    eval_str: str = "?"
    eval_category: str = "unclear"
    pv_san: list[str] = Field(default_factory=list)
    facts: dict = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    fen: str
    best_move_uci: str
    best_move_san: str
    best_pv_san: list[str] = Field(default_factory=list)
    best_pv_uci: list[str] = Field(default_factory=list)
    eval_cp: Optional[int] = None
    mate: Optional[int] = None
    win_pct: Optional[float] = None
    eval_str: str = "?"
    depth_reached: int
    depth_requested: int = 22
    pv_lines: list[PvLine]
    explanation: Optional[WhyExplanation] = Field(
        default=None, description="Deterministic, engine-grounded why (no LLM needed)"
    )
    nodes: Optional[int] = None
    nps: Optional[int] = None
    is_terminal: bool = False
    terminal_result: Optional[str] = None
    turn: str = "white"
    engine: str = "stockfish"
    cached: bool = False
    elapsed_s: Optional[float] = None


class VerifyRequest(BaseModel):
    text: str = Field(description="LLM explanation to verify")
    fen: str
    pv_sans: list[str] = Field(default_factory=list)
    pv_sequences: Optional[list[list[str]]] = None


class ErrorResponse(BaseModel):
    detail: str
    code: str = "engine_error"
