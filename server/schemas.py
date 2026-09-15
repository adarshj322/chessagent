"""Shared Pydantic schemas for the Stockfish analyze API."""

from typing import Literal, Optional

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


class AnalyzeResponse(BaseModel):
    fen: str
    best_move_uci: str
    best_move_san: str
    eval_cp: Optional[int] = None
    mate: Optional[int] = None
    depth_reached: int
    pv_lines: list[PvLine]
    nodes: Optional[int] = None
    nps: Optional[int] = None
    engine: str = "stockfish"


class ErrorResponse(BaseModel):
    detail: str
    code: Literal["bad_fen", "engine_missing", "engine_timeout", "engine_error"] = "engine_error"
