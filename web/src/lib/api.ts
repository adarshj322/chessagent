export interface PvLine {
  uci: string;
  san: string;
  eval_cp: number | null;
  mate: number | null;
}

export interface AnalyzeResponse {
  fen: string;
  best_move_uci: string;
  best_move_san: string;
  eval_cp: number | null;
  mate: number | null;
  depth_reached: number;
  pv_lines: PvLine[];
  nodes?: number | null;
  nps?: number | null;
  engine: string;
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
