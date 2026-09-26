/**
 * streamClient.ts — SSE client for the Safety Copilot streaming endpoint.
 *
 * POST /api/copilot/chat/stream emits Server-Sent Events:
 *   {"type":"stage","stage":"RETRIEVE","label":"...","status":"active"}
 *   {"type":"stage_done","stage":"RETRIEVE","duration_ms":42}
 *   {"type":"token","content":"partial answer text"}
 *   {"type":"complete","answer":"...","model":"...","data_source":"...","grounding":{...}}
 *   {"type":"error","message":"..."}
 *
 * This client surfaces REAL backend progress only — no simulated delays.
 * If the backend does not support streaming (404) the caller falls back to
 * the blocking /api/copilot/chat endpoint.
 */

import { getApiUrl } from './api';

export type CopilotStageId =
  | 'SANITIZE' | 'UNDERSTAND' | 'RETRIEVE' | 'SIF_ANALYSIS'
  | 'BARRIER_ANALYSIS' | 'PATTERN_ANALYSIS' | 'EVIDENCE' | 'GENERATION';

export interface CopilotStreamEvent {
  type: 'stage' | 'stage_done' | 'token' | 'complete' | 'error';
  stage?: CopilotStageId;
  label?: string;
  status?: string;
  duration_ms?: number;
  content?: string;
  message?: string;
  answer?: string;
  model?: string;
  data_source?: string;
  source_reports?: string[];
  pii_detected_in_question?: boolean;
  grounding?: Record<string, unknown>;
}

export interface CopilotStreamHandlers {
  onEvent: (event: CopilotStreamEvent) => void;
  signal?: AbortSignal;
}

export interface CopilotStreamInput {
  message: string;
  history?: Array<{ role: 'user' | 'assistant'; content: string }>;
}

export async function streamCopilotChat(
  input: CopilotStreamInput,
  handlers: CopilotStreamHandlers,
): Promise<void> {
  const token = localStorage.getItem('safesense_token');
  // getApiUrl() honors VITE_API_BASE_URL (split-origin Render deployment).
  const res = await fetch(getApiUrl('/copilot/chat/stream'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message: input.message, history: input.history ?? [] }),
    signal: handlers.signal,
  });

  if (res.status === 401) {
    const err = new Error('Your session has expired. Please sign in again.') as Error & { status?: number };
    err.status = 401;
    throw err;
  }
  if (!res.ok || !res.body) {
    let detail = `Copilot stream unavailable (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; each data line starts with "data: "
      let sep: number;
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        for (const line of frame.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            handlers.onEvent(JSON.parse(line.slice(6)) as CopilotStreamEvent);
          } catch {
            // malformed frame — skip rather than crash the stream
          }
        }
      }
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}
