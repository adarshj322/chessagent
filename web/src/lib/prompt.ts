import type { PvLine } from './api';

export interface WhyPayload {
  verdict: string;
  why: { kind: string; text: string }[];
  threats: string[];
  alternatives: { san?: string | null; why?: string | null }[];
}

export function buildSystemPrompt(rating = 1200): string {  const level = rating < 1000 ? 'beginner' : rating < 1600 ? 'intermediate' : 'advanced';
  return (
    `You are a chess coach explaining a Stockfish analysis to a ${level} player (rating ~${rating}).\n` +
    'You are given VERIFIED_FACTS computed by a chess engine from the real board. ' +
    'They are always correct. Your job is ONLY to rephrase them clearly.\n' +
    'STRICT RULES:\n' +
    '1. Only discuss moves that appear in ENGINE_PVS or VERIFIED_FACTS. Never invent variations.\n' +
    '2. Never invent evaluations, mate counts, or threats — reuse the numbers given.\n' +
    '3. If the position is quiet/positional, say so instead of inventing tactics.\n' +
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
  mate: number | null = null,
  why: WhyPayload | null = null
): string {
  const pvs = pvLines
    .map((p, i) => {
      const seq = (p.pv_san?.length ? p.pv_san : [p.san]).slice(0, 6).join(' ');
      const loss = i > 0 && p.eval_loss_cp != null ? ` eval_loss=${(p.eval_loss_cp / 100).toFixed(2)}p` : '';
      return `PV${i + 1}: ${seq} (first ${p.san} ${p.uci}) eval=${formatEval(p.eval_cp, p.mate)}${loss}`;
    })
    .join('\n');
  let facts = '';
  if (why) {
    const wl = why.why.map((b) => `- [${b.kind}] ${b.text}`).join('\n') || '- (quiet best move)';
    const th = why.threats.map((t) => `- ${t}`).join('\n') || '- none forced';
    const al = why.alternatives.map((a) => `- ${a.san}: ${a.why}`).join('\n') || '- no alternatives given';
    facts =
      `\nVERIFIED_FACTS (always true — rephrase, do not contradict):\n` +
      `Verdict: ${why.verdict}\nWhy:\n${wl}\nThreats:\n${th}\nAlternatives:\n${al}\n`;
  }
  return (
    `Position FEN: ${fen}\n` +
    `Engine: Stockfish, depth ${depth}\n` +
    `Top-line eval (side to move): ${formatEval(evalCp, mate)}\n` +
    `ENGINE_PVS (only moves you may cite):\n${pvs}\n` +
    facts +
    `Student rating: ~${rating}\n` +
    'Explain the best move (PV1) vs PV2/PV3, following VERIFIED_FACTS.'
  );
}

/** System prompt for follow-up chat: same grounding, plus multi-turn rules. */
export function buildChatSystemPrompt(rating = 1200): string {
  return (
    buildSystemPrompt(rating) +
    '\nFOLLOW-UP RULES:\n' +
    '6. This is a continuing conversation about ONE position. Every reply must still obey rules 1-4.\n' +
    '7. If asked about a different position or general theory, answer briefly (max 3 sentences) and steer back to this position.\n' +
    '8. Never carry a move mentioned by the student into your answer as if the engine recommended it — only ENGINE_PVS moves count.'
  );
}

/**
 * Short grounding nudge appended to every follow-up question. The full
 * ENGINE_PVS + VERIFIED_FACTS already sit earlier in the history; this keeps
 * them salient so long chats don't drift into hallucination.
 */
export function buildFollowupReminder(pvSans: string[], verdict: string): string {
  const moves = pvSans.length ? pvSans.join(', ') : '(none)';
  return (
    `\n[Grounding reminder — still true for this position. ` +
    `Verdict: ${verdict} Moves you may cite: ${moves}. Only cite these.]`
  );
}

/** Correction prompt used for the single automatic retry after a failed verification. */
export function buildCorrectionPrompt(badMoves: string[], pvSans: string[]): string {
  const moves = pvSans.length ? pvSans.join(', ') : '(none)';
  return (
    `You just cited ${badMoves.join(', ')} — none of these appear in ENGINE_PVS and they are not legal here. ` +
    `Correct your answer now using only these engine moves: ${moves}. Do not mention the wrong moves again.`
  );
}
