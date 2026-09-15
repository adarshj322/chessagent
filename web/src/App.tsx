import { useMemo, useState } from 'react';
import { Chess } from 'chess.js';
import { Chessboard } from 'react-chessboard';
import ReactMarkdown from 'react-markdown';
import { analyzePosition, formatEval, type AnalyzeResponse } from './lib/api';
import { buildSystemPrompt, buildUserPrompt } from './lib/prompt';
import { explainStream, fetchModels, loadKey, saveKey, MODEL_STORE } from './lib/openrouter';
import { verifyExplanation } from './lib/verify';

const STARTPOS = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export default function App() {
  const [fen, setFen] = useState(STARTPOS);
  const [depth, setDepth] = useState(22);
  const [multipv, setMultipv] = useState(3);
  const [rating, setRating] = useState(1200);
  const [engine, setEngine] = useState<AnalyzeResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [apiKey, setApiKey] = useState(loadKey());
  const [model, setModel] = useState(localStorage.getItem(MODEL_STORE) ?? 'openai/gpt-4o-mini');
  const [models, setModels] = useState<string[]>([]);
  const [explanation, setExplanation] = useState('');
  const [explaining, setExplaining] = useState(false);

  const game = useMemo(() => {
    try {
      return new Chess(fen);
    } catch {
      return new Chess();
    }
  }, [fen]);

  const verification = useMemo(
    () => (explanation && engine ? verifyExplanation(explanation, engine.pv_lines.map((p) => p.san)) : null),
    [explanation, engine]
  );

  function onDrop(source: string, target: string): boolean {
    try {
      const g = new Chess(fen);
      g.move({ from: source, to: target, promotion: 'q' });
      setFen(g.fen());
      setEngine(null);
      setExplanation('');
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
    try {
      const system = buildSystemPrompt(rating);
      const user = buildUserPrompt(fen, engine.pv_lines, engine.depth_reached, rating, engine.eval_cp, engine.mate);
      let acc = '';
      await explainStream(apiKey, model, system, user, (t) => {
        acc += t;
        setExplanation(acc);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExplaining(false);
    }
  }

  const evalPct = engine ? Math.min(95, Math.max(5, 50 + (engine.eval_cp ?? 0) / 8)) : 50;

  return (
    <div>
      <header style={{ padding: '16px 20px 0', maxWidth: 1200, margin: '0 auto' }}>
        <h2 style={{ margin: '4px 0' }}>Stockfish Move Analyzer</h2>
        <p style={{ margin: 0, opacity: 0.75 }}>
          Engine finds the best move on the server. Any OpenRouter model explains why — with your own key.
        </p>
      </header>
      <div className="layout">
        <div>
          <div className="card">
            <Chessboard position={fen} onPieceDrop={onDrop} boardWidth={Math.min(440, window.innerWidth - 60)} />
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => { setFen(STARTPOS); setEngine(null); setExplanation(''); }}>Reset</button>
              <button onClick={() => { const g = new Chess(fen); g.undo(); setFen(g.fen()); }}>Undo</button>
              <button onClick={() => navigator.clipboard?.writeText(fen)}>Copy FEN</button>
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
                <div><strong>Best:</strong> <span className="mono">{engine.best_move_san} ({engine.best_move_uci})</span> <strong>{formatEval(engine.eval_cp, engine.mate)}</strong></div>
                <div className="evalbar"><div style={{ width: `${evalPct}%` }} /></div>
                <div className="mono">depth {engine.depth_reached} · {engine.nodes ?? '?'} nodes · {engine.nps ?? '?'} nps</div>
                <ol className="mono">{engine.pv_lines.map((p, i) => <li key={i}>{p.san} ({p.uci}) — {formatEval(p.eval_cp, p.mate)}</li>)}</ol>
              </div>
            )}
          </div>
        </div>
        <div>
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
              <button className="primary" disabled={explaining || !engine} onClick={onExplain}>{explaining ? 'Explaining…' : 'Explain with LLM'}</button>
            </div>
            <p style={{ opacity: 0.7, fontSize: 13 }}>Turn: {game.turn() === 'w' ? 'White' : 'Black'} to move. Engine data is injected into the prompt; the model may only cite those lines.</p>
            {explanation && <div className="card"><ReactMarkdown>{explanation}</ReactMarkdown></div>}
            {verification && verification.unverified.length > 0 && (
              <div className="warn">Unverified move mentions (not in engine lines, treat with caution): <span className="mono">{verification.unverified.join(', ')}</span></div>
            )}
            {verification && verification.unverified.length === 0 && verification.verified.length > 0 && (
              <div className="warn" style={{ background: '#e8f5e9', borderColor: '#a5d6a7' }}>All cited moves verified against engine lines: <span className="mono">{verification.verified.join(', ')}</span></div>
            )}
          </div>
          {error && <div className="err">{error}</div>}
          <div className="card">
            <h4>How it works</h4>
            <ol style={{ fontSize: 14 }}>
              <li>Make moves on the board (or paste FEN).</li>
              <li>Analyze → backend Stockfish returns best move + PVs + eval at your chosen depth.</li>
              <li>Explain → browser calls OpenRouter directly with engine JSON + rating-aware prompt.</li>
              <li>Check the verification badge — any non-engine move is flagged.</li>
            </ol>
            <p className="mono" style={{ fontSize: 12 }}>API: POST /api/analyze {'{fen, depth≤28, multipv≤5}'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
