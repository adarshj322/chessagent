// Note: no trailing \b — it would drop check/mate suffixes (+/#).
const SAN_RE = /\b(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?)[+#]?/g;

/** Extract SAN-looking tokens and split into verified (in engine PVs) vs unverified. */
export function verifyExplanation(text: string, pvSans: string[]): { verified: string[]; unverified: string[] } {
  const tokens = text.match(SAN_RE) ?? [];
  const pvSet = new Set(pvSans.map((s) => s.replace(/[+#]$/, '')));
  const verified: string[] = [];
  const unverified: string[] = [];
  for (const t of tokens) {
    const base = t.replace(/[+#]$/, '');
    // Strict MVP rule: only engine PV moves count as verified.
    // (Backend also accepts any legal move; frontend stays strict to catch hallucinations.)
    if (pvSet.has(base)) verified.push(t);
    else unverified.push(t);
  }
  return { verified, unverified };
}
