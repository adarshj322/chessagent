import type { PvLine } from './api';

export function buildSystemPrompt(rating = 1200): string {
  const level = rating < 1000 ? 'beginner' : rating < 1600 ? 'intermediate' : 'advanced';
  return (
    `You are a concise chess coach explaining a Stockfish analysis to a ${level} player (rating ~${rating}).\n` +
    'STRICT RULES:\n' +
    '1. Only discuss moves that appear in ENGINE_PVS or are legal replies to them.\n' +
    '2. Never invent variations, evaluations, or threats not supported by the engine data.\n' +
    '3. If the position is unclear, say so instead of guessing.\n' +
    '4. Keep tactics concrete (squares + pieces), avoid purple prose.\n' +
    'Output markdown with exactly these sections:\n' +
    '## Verdict (1 line)\n## Why this move\n## Threats & ideas\n## Why not the alternatives'
  );
}

export function formatEval(evalCp: number | null, mate: number | null): string {
  if (mate !== null && mate !== undefined) return mate > 0 ? `M${mate}` : `-M${Math.abs(mate)}`;
  if (evalCp === null || evalCp === undefined) return '?';
  const p = evalCp / 100;
  return `${p >= 0 ? '+' : ''}${p.toFixed(2)}`;
}

export function buildUserPrompt(
  fen: string,
  pvLines: PvLine[],
  depth: number,
  rating = 1200,
  evalCp: number | null = null,
  mate: number | null = null
): string {
  const pvs = pvLines
    .map((p, i) => `PV${i + 1}: ${p.san} (${p.uci}) eval=${formatEval(p.eval_cp, p.mate)}`)
    .join('\n');
  return (
    `Position FEN: ${fen}\n` +
    `Engine: Stockfish, depth ${depth}\n` +
    `Top-line eval (side to move): ${formatEval(evalCp, mate)}\n` +
    `ENGINE_PVS (only moves you may cite):\n${pvs}\n` +
    `Student rating: ~${rating}\n` +
    'Explain the best move (PV1) vs PV2/PV3.'
  );
}
