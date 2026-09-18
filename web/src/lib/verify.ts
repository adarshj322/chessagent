import { Chess } from 'chess.js';

// Note: no trailing \b — it would drop check/mate suffixes (+/#).
const SAN_RE = /\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?/g;

export interface TieredVerification {
  engineMoves: string[];
  legalOther: string[];
  hallucinated: string[];
}

function norm(s: string): string {
  return s.replace(/[+#]$/, '');
}

/**
 * 3-tier check (mirrors server/verify.py):
 * engineMoves = cited from a Stockfish PV (safe),
 * legalOther = legal but not engine-recommended (amber),
 * hallucinated = neither (treat with caution).
 */
export function verifyExplanation(
  text: string,
  pvSans: string[],
  fen?: string,
  pvSequences?: string[][]
): TieredVerification {
  const tokens = text.match(SAN_RE) ?? [];
  const pvSet = new Set(pvSans.map(norm));
  if (pvSequences) for (const seq of pvSequences) for (const s of seq ?? []) pvSet.add(norm(s));

  let legal = new Set<string>();
  if (fen) {
    try {
      const c = new Chess(fen);
      legal = new Set(c.moves().map(norm));
    } catch {
      legal = new Set();
    }
  }

  const engineMoves: string[] = [];
  const legalOther: string[] = [];
  const hallucinated: string[] = [];
  for (const t of tokens) {
    const base = norm(t);
    if (pvSet.has(base)) engineMoves.push(t);
    else if (legal.has(base)) legalOther.push(t);
    else hallucinated.push(t);
  }
  return { engineMoves, legalOther, hallucinated };
}
