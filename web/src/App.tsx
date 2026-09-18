import { useEffect, useMemo, useState } from 'react';
import { Chess, type Square } from 'chess.js';
import { Chessboard } from 'react-chessboard';
import ReactMarkdown from 'react-markdown';
import { analyzePosition, evalBarPct, type AnalyzeResponse } from './lib/api';
import { buildSystemPrompt, buildUserPrompt } from './lib/prompt';
import { explainStream, fetchModels, loadKey, saveKey, MODEL_STORE, EFFORT_STORE, type ReasoningEffort } from './lib/openrouter';
import { verifyExplanation } from './lib/verify';

const STARTPOS = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const EXAMPLES: { name: string; fen: string }[] = [
  { name: 'Start position', fen: STARTPOS },
  { name: 'Italian Game', fen: 'r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3' },
  { name: "Scholar's mate in 1", fen: 'r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4' },
  { name: 'Endgame: king + pawn', fen: '8/8/4k3/8/8/4K3/4P3/8 w - - 0 1' },
];

const KIND_COLORS: Record<string, string> = {
  mate: '#c62828',
  check: '#ef6c00',
  material: '#2e7d32',
  tactic: '#1565c0',
  safety: '#6a1b9a',
  positional: '#546e7a',
  danger: '#b71c1c',
};

function uciSquares(uci: string): [Square, Square] | null {
  if (!uci || uci.length < 4) return null;
  return [uci.slice(0, 2) as Square, uci.slice(2, 4) as Square];
}

export default function App() {
  const [fen, setFen] = useState(STARTPOS);
  const [depth, setDepth] = useState(22);
  const [multipv, setMultipv] = useState(3);
  const [rating, setRating] = useState(1200);
  const [engine, setEngine] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [orientation, setOrientation] = useState<'white' | 'black'>('white');

  // PV preview: step through a line without losing the base position.
  const [selPv, setSelPv] = useState(0);
  const [ply, setPly] = useState(0);

  const [apiKey, setApiKey] = useState(loadKey());
  const [model, setModel] = useState(localStorage.getItem(MODEL_STORE) ?? 'openai/gpt-4o-mini');
  const [effort, setEffort] = useState<ReasoningEffort>((localStorage.getItem(EFFORT_STORE) as ReasoningEffort) ?? '');
  const [models, setModels] = useState<string[]>([]);
  const [explanation, setExplanation] = useState('');
  const [explaining, setExplaining] = useState(false);

  useEffect(() => {
    setSelPv(0);
    setPly(0);
  }, [engine]);

  const game = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return new Chess();
    }
  }, [fen]);

  const previewFen = useMemo(() => {
    if (!engine || ply === 0) return fen;
    try {
      const c = new Chess(engine.fen);
      const seq = engine.pv_lines[Math.min(selPv, engine.pv_lines.length - 1)]?.pv_san ?? [];
      for (const san of seq.slice(0, ply)) c.move(san);
      return c.fen();
    } catch {
      return fen;
    }
  }, [engine, ply, selPv, fen]);

  const previewLen = engine ? (engine.pv_lines[Math.min(selPv, engine.pv_lines.length - 1)]?.pv_san.length ?? 0) : 0;

  const verification = useMemo(() => {
    if (!explanation || !engine) return null;
    return verifyExplanation(
      explanation,
      engine.pv_lines.map((p) => p.san),
      engine.fen,
      engine.pv_lines.map((p) => p.pv_san)
    );
  }, [explanation, engine]);

  const arrows = useMemo(() => {
    if (!engine || ply !== 0) return [];
    const out: [Square, Square, string?][] = [];
    const b = uciSquares(engine.best_move_uci);
    if (b) out.push([b[0], b[1], 'rgba(46,125,50,0.85)']);
    if (engine.pv_lines[1]) {
      const s = uciSquares(engine.pv_lines[1].uci);
      if (s) out.push([s[0], s[1], 'rgba(239,108,0,0.8)']);
    }
    return out;
  }, [engine, ply]);

  function resetAnalysis() {
    setEngine(null);
    setExplanation('');
    setPly(0);
  }

  function onDrop(source: string, target: string): boolean {
    try {
      const g = new Chess(previewFen);
      g.move({ from: source, to: target, promotion: 'q' });
      setFen(g.fen());
      resetAnalysis();
      return true;
    } catch {
      return false;
    }
  }

  async function onAnalyze() {
    setBusy(true);
    setError('');
    try {
      const res = await analyzePosition(fen, depth, multipv);
      setEngine(res);
      setPly(0);
      // Auto-orient to side to move for study comfort? Keep user's choice.
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onLoadModels() {
    setError('');
    try {
      saveKey(apiKey);
      const list = await fetchModels(apiKey);
      setModels(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onExplain() {
    if (!engine) {
      setError('Run engine analysis first.');
      return;
    }
    if (!apiKey) {
      setError('Enter your OpenRouter API key first (stored only in this browser).');
      return;
    }
    setExplaining(true);
    setError('');
    setExplanation('');
    localStorage.setItem(MODEL_STORE, model);
    localStorage.setItem(EFFORT_STORE, effort);
    try {
      const system = buildSystemPrompt(rating);
      const user = buildUserPrompt(fen, engine.pv_lines, engine.depth_reached, rating, engine.eval_cp, engine.mate, engine.explanation);
      let acc = '';
      await explainStream(apiKey, model, system, user, (t) => {
        acc += t;
        setExplanation(acc);
      }, { effort });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExplaining(false);
    }
  }

  const barPct = engine ? evalBarPct(engine.eval_cp, engine.mate, engine.win_pct) : 50;
  const why = engine?.explanation ?? null;

  return (
    <div>
      <header style={{ padding: '16px 20px 0', maxWidth: 1200, margin: '0 auto' }}>
        <h2 style={{ margin: '4px 0' }}>Stockfish Move Analyzer</h2>
        <p style={{ margin: 0, opacity: 0.75 }}>
          Engine finds the best move on the server. <strong>Verified facts</strong> explain why — always correct,
          no key needed. An optional LLM rephrases them for your level, with every cited move checked.
        </p>
      </header>
      <div className="layout">
        <div>
          <div className="card">
            <Chessboard
              position={previewFen}
              onPieceDrop={onDrop}
              boardOrientation={orientation}
              customArrows={arrows}
              boardWidth={Math.min(440, window.innerWidth - 60)}
            />
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => { setFen(STARTPOS); resetAnalysis(); }}>Reset</button>
              <button onClick={() => {
                if (ply > 0) { setPly(ply - 1); return; }
                try { const g = new Chess(fen); g.undo(); setFen(g.fen()); resetAnalysis(); } catch { /* noop */ }
              }}>Undo</button>
              <button onClick={() => setOrientation(orientation === 'white' ? 'black' : 'white')}>Flip</button>
              <button onClick={() => navigator.clipboard?.writeText(fen)}>Copy FEN</button>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              <select
                value={EXAMPLES.find((e) => e.fen === fen)?.name ?? ''}
                onChange={(e) => {
                  const ex = EXAMPLES.find((x) => x.name === e.target.value);
                  if (ex) { setFen(ex.fen); resetAnalysis(); }
                }}
              >
                <option value="" disabled>Try an example…</option>
                {EXAMPLES.map((e) => <option key={e.name} value={e.name}>{e.name}</option>)}
              </select>
            </div>
            <input style={{ width: '100%', marginTop: 8 }} className="mono" value={fen} onChange={(e) => setFen(e.target.value)} spellCheck={false} />
          </div>
          <div className="card">
            <h3>Engine (server Stockfish)</h3>
            <div className="row">
              <label>Depth {depth} <input type="range" min={12} max={28} value={depth} onChange={(e) => setDepth(Number(e.target.value))} /></label>
              <label>Lines <select value={multipv} onChange={(e) => setMultipv(Number(e.target.value))}><option value={1}>1</option><option value={3}>3</option><option value={5}>5</option></select></label>
              <button className="primary" disabled={busy} onClick={onAnalyze}>{busy ? 'Analyzing…' : 'Analyze'}</button>
            </div>
            {engine && (
              <div style={{ marginTop: 8 }}>
                <div>
                  <strong>Best:</strong> <span className="mono">{engine.best_move_san} ({engine.best_move_uci})</span>{' '}
                  <strong>{engine.eval_str}</strong>
                  {engine.win_pct != null && engine.mate == null && <span className="mono"> · {engine.win_pct}%</span>}
                  {engine.cached && <span className="mono"> · cached</span>}
                </div>
                <div className="evalbar" title="Win probability for side to move"><div style={{ width: `${barPct}%` }} /></div>
                <div className="mono">
                  depth {engine.depth_reached} · {engine.nodes ?? '?'} nodes · {engine.nps ?? '?'} nps · {(engine.elapsed_s ?? 0).toFixed(2)}s
                </div>
                {engine.is_terminal && <div className="warn">Terminal position: {engine.terminal_result ?? 'game over'}.</div>}
                <ol className="mono">
                  {engine.pv_lines.map((p, i) => (
                    <li key={i} className={i === selPv ? 'pvsel' : ''} onClick={() => { setSelPv(i); setPly(0); }} style={{ cursor: 'pointer' }}>
                      <strong>{p.san}</strong> ({p.uci}) — {p.eval_str}
                      {p.eval_loss_cp != null && i > 0 && <span> (−{(p.eval_loss_cp / 100).toFixed(2)})</span>}
                      <br />
                      <span className="pvseq">{p.pv_san.slice(0, 6).join(' ')}</span>
                    </li>
                  ))}
                </ol>
                {previewLen > 0 && (
                  <div className="row">
                    <button disabled={ply === 0} onClick={() => setPly(0)}>Base</button>
                    <button disabled={ply === 0} onClick={() => setPly(Math.max(0, ply - 1))}>‹ Prev</button>
                    <span className="mono">move {ply}/{previewLen}</span>
                    <button disabled={ply >= previewLen} onClick={() => setPly(Math.min(previewLen, ply + 1))}>Next ›</button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <div>
          <div className="card">
            <h3>Why this move <span className="badge-ok">verified · no key needed</span></h3>
            {!engine && <p style={{ opacity: 0.7 }}>Run <strong>Analyze</strong> — every bullet below is computed from the real board + Stockfish numbers, so it is always correct.</p>}
            {why && (
              <div>
                <p className="verdict">{why.verdict}</p>
                <ul className="why">
                  {why.why.map((b, i) => (
                    <li key={i}>
                      <span className="kind" style={{ background: KIND_COLORS[b.kind] ?? '#546e7a' }}>{b.kind}</span> {b.text}
                    </li>
                  ))}
                </ul>
                {why.threats.length > 0 && (
                  <>
                    <h4>Threats &amp; ideas</h4>
                    <ul className="why">{why.threats.map((t, i) => <li key={i}>{t}</li>)}</ul>
                  </>
                )}
                {why.alternatives.length > 0 && (
                  <>
                    <h4>Why not the alternatives</h4>
                    <ul className="why">
                      {why.alternatives.map((a, i) => (
                        <li key={i}><span className="mono"><strong>{a.san}</strong> ({a.eval_str})</span> — {a.why}</li>
                      ))}
                    </ul>
                  </>
                )}
                <p className="mono" style={{ fontSize: 12, opacity: 0.7 }}>
                  {why.eval_category} · main line: {why.pv_san.slice(0, 6).join(' ')}
                </p>
              </div>
            )}
          </div>
          <div className="card">
            <h3>Explanation (OpenRouter BYOK — key never leaves your browser)</h3>
            <div className="row">
              <input type="password" placeholder="sk-or-v1-…" value={apiKey} onChange={(e) => setApiKey(e.target.value)} style={{ flex: 1, minWidth: 220 }} />
              <button onClick={onLoadModels}>Validate + load models</button>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              {models.length > 0 ? (
                <select value={model} onChange={(e) => setModel(e.target.value)} style={{ flex: 1 }}>{models.map((m) => <option key={m} value={m}>{m}</option>)}</select>
              ) : (
                <input value={model} onChange={(e) => setModel(e.target.value)} style={{ flex: 1 }} placeholder="openai/gpt-4o-mini" />
              )}
              <label>Rating <input type="number" value={rating} min={400} max={2800} step={100} onChange={(e) => setRating(Number(e.target.value))} style={{ width: 90 }} /></label>
              <label title="How hard the model thinks before answering. Higher = better on tricky tactics, but slower and more tokens. Ignored by models without reasoning support.">Reasoning <select value={effort} onChange={(e) => setEffort(e.target.value as ReasoningEffort)}>
                <option value="">Off</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="xhigh">Max</option>
              </select></label>
              <button className="primary" disabled={explaining || !engine} onClick={onExplain}>{explaining ? 'Explaining…' : 'Explain with LLM'}</button>
            </div>
            <p style={{ opacity: 0.7, fontSize: 13 }}>
              Turn: {game.turn() === 'w' ? 'White' : 'Black'} to move. The model only rephrases the verified facts above;
              every cited move is checked against the engine lines.
            </p>
            {explanation && <div className="card"><ReactMarkdown>{explanation}</ReactMarkdown></div>}
            {verification && verification.hallucinated.length > 0 && (
              <div className="warn">Unverified mentions (not in engine lines or legal moves — treat with caution): <span className="mono">{verification.hallucinated.join(', ')}</span></div>
            )}
            {verification && verification.hallucinated.length === 0 && verification.legalOther.length > 0 && (
              <div className="warn" style={{ background: '#fff8e1', borderColor: '#e0c36a' }}>
                Legal but not engine-recommended mentions: <span className="mono">{verification.legalOther.join(', ')}</span>
                {verification.engineMoves.length > 0 && <> · engine moves OK: <span className="mono">{verification.engineMoves.join(', ')}</span></>}
              </div>
            )}
            {verification && verification.hallucinated.length === 0 && verification.legalOther.length === 0 && verification.engineMoves.length > 0 && (
              <div className="warn" style={{ background: '#e8f5e9', borderColor: '#a5d6a7' }}>All cited moves verified against engine lines: <span className="mono">{verification.engineMoves.join(', ')}</span></div>
            )}
          </div>
          {error && <div className="err">{error}</div>}
          <div className="card">
            <h4>How it works</h4>
            <ol style={{ fontSize: 14 }}>
              <li>Make moves on the board (or paste FEN / try an example).</li>
              <li>Analyze → backend Stockfish returns best move + full lines + eval at your chosen depth.</li>
              <li>Read <strong>Why this move</strong> — deterministic facts, always correct, no key needed.</li>
              <li>Optionally Explain → any OpenRouter model rephrases those facts for your rating; citations are verified.</li>
              <li>Click a PV line, then step Next/Prev to walk the variation on the board.</li>
            </ol>
            <p className="mono" style={{ fontSize: 12 }}>API: POST /api/analyze {'{fen, depth≤28, multipv≤5}'} · POST /api/verify · GET /api/health</p>
          </div>
        </div>
      </div>
    </div>
  );
}
