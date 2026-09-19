const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions';
const MODELS_URL = 'https://openrouter.ai/api/v1/models';

export const KEY_STORE = 'sma.openrouter.key';
export const MODEL_STORE = 'sma.openrouter.model';
export const EFFORT_STORE = 'sma.openrouter.effort';

export type ReasoningEffort = '' | 'low' | 'medium' | 'high' | 'xhigh';

export function loadKey(): string {
  return localStorage.getItem(KEY_STORE) ?? '';
}

export function saveKey(k: string) {
  if (k) localStorage.setItem(KEY_STORE, k);
  else localStorage.removeItem(KEY_STORE);
}

export async function fetchModels(apiKey: string): Promise<string[]> {
  const res = await fetch(MODELS_URL, { headers: { Authorization: `Bearer ${apiKey}` } });
  if (!res.ok) throw new Error(`Model list failed (${res.status}). Check API key.`);
  const data = await res.json();
  return (data.data ?? []).map((m: { id: string }) => m.id).slice(0, 200);
}

export async function explainStream(
  apiKey: string,
  model: string,
  system: string,
  user: string,
  onToken: (t: string) => void,
  opts: { effort?: ReasoningEffort } = {}
): Promise<void> {
  return chatStream(
    apiKey,
    model,
    [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    onToken,
    opts
  );
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/** Multi-turn streaming chat (used for follow-up questions). */
export async function chatStream(
  apiKey: string,
  model: string,
  messages: ChatMessage[],
  onToken: (t: string) => void,
  opts: { effort?: ReasoningEffort } = {}
): Promise<void> {
  // OpenRouter normalizes reasoning controls across providers:
  // https://openrouter.ai/docs/use-cases/reasoning-tokens
  // Models that don't support `effort` simply ignore it.
  // NOTE: we only stream delta.content, so hidden chain-of-thought never
  // leaks into the explanation — you pay reasoning tokens, not reading time.
  const body: Record<string, unknown> = {
    model,
    stream: true,
    temperature: 0.2,
    messages
  };
  if (opts.effort) body.reasoning = { effort: opts.effort };
  const res = await fetch(OPENROUTER_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
      'HTTP-Referer': window.location.origin,
      'X-Title': 'Stockfish Move Analyzer'
    },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error('Invalid OpenRouter API key (401).');
    if (res.status === 402) throw new Error('Insufficient OpenRouter credits (402). Top up at openrouter.ai.');
    if (res.status === 429) throw new Error('Rate limited (429). Try again or pick another model.');
    throw new Error(`OpenRouter request failed (${res.status}).`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('Streaming not supported in this browser.');
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith('data:')) continue;
      const payload = t.slice(5).trim();
      if (payload === '[DONE]') return;
      try {
        const json = JSON.parse(payload);
        const delta = json.choices?.[0]?.delta?.content ?? '';
        if (delta) onToken(delta);
      } catch {
        /* ignore partial chunks */
      }
    }
  }
}
