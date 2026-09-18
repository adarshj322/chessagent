export interface PvLine {
  uci: string;
  san: string;
  eval_cp: number | null;
  mate: number | null;
  win_pct: number | null;
  eval_str: string;
  eval_loss_cp: number | null;
  pv_san: string[];
  pv_uci: string[];
  depth?: number | null;
}

export interface WhyBullet {
  kind: string;
  text: string;
}

export interface Alternative {
  san?: string | null;
  uci?: string | null;
  eval_str?: string | null;
  why: string;
}

export interface WhyExplanation {
  verdict: string;
  why: WhyBullet[];
  threats: string[];
  alternatives: Alternative[];
  eval_str: string;
  eval_category: string;
  pv_san: string[];
  facts: Record<string, unknown>;
}

export interface AnalyzeResponse {
  fen: string;
  best_move_uci: string;
  best_move_san: string;
  best_pv_san: string[];
  best_pv_uci: string[];
  eval_cp: number | null;
  mate: number | null;
  win_pct: number | null;
  eval_str: string;
  depth_reached: number;
  depth_requested: number;
  pv_lines: PvLine[];
  explanation: WhyExplanation | null;
  nodes?: number | null;
  nps?: number | null;
  is_terminal: boolean;
  terminal_result?: string | null;
  turn: string;
  engine: string;
  cached?: boolean;
  elapsed_s?: number | null;
}

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export async function analyzePosition(fen: string, depth: number, multipv: number): Promise<AnalyzeResponse> {
  const res = await fetch(`${API_BASE}/api/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fen, depth, multipv })
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Engine request failed (${res.status})`);
  }
  return res.json();
}

export function formatEval(evalCp: number | null, mate: number | null): string {
  if (mate !== null && mate !== undefined) return mate > 0 ? `M${mate}` : `-M${Math.abs(mate)}`;
  if (evalCp === null || evalCp === undefined) return '?';
  const p = evalCp / 100;
  return `${p >= 0 ? '+' : ''}${p.toFixed(2)}`;
}

/** 0-100 bar fill for the side to move (uses server win% when present). */
export function evalBarPct(evalCp: number | null, mate: number | null, winPct: number | null): number {
  if (mate !== null && mate !== undefined) return mate > 0 ? 98 : 2;
  if (winPct !== null && winPct !== undefined) return Math.min(97, Math.max(3, winPct));
  const cp = evalCp ?? 0;
  const win = 50 + 50 * (2 / (1 + Math.exp(-0.00368208 * cp)) - 1);
  return Math.min(97, Math.max(3, win));
}
