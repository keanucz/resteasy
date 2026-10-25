/** Calls to the FastAPI backend, signed with the app's Supabase login (never an agent token). */

import { env } from '@/config/env';
import { supabase } from '@/services/supabase/client';

/** How long a body-less backend call may take before it fails. */
const API_TIMEOUT_MS = 10_000;
/** How long a call with a JSON body may take: a save, or a voice preview the backend has to speak. */
const API_WRITE_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * Fetch `path` (after /api) with the current login's access token when there is one, for any body
 * (JSON, a recording to upload) and any answer (JSON, audio). Throws an ApiError for a non-2xx
 * answer. `signal` lets the caller stop the request itself (an upload's own time limit, say).
 */
export async function authedFetch(
  path: string,
  init: {
    method?: string;
    headers?: Record<string, string>;
    body?: BodyInit;
    signal?: AbortSignal;
    /** Overrides the default time limit, for a call the backend is known to take long over. */
    timeoutMs?: number;
  } = {},
): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  // A backend the phone can't reach may never answer; give up rather than leave a screen waiting.
  // A JSON body (a save, a spoken preview) gets longer; uploads (any other body) are never cut short
  // here. Either limit or the caller's own signal stops the request, whichever comes first.
  const abort = new AbortController();
  const stop = () => abort.abort();
  if (init.signal?.aborted) stop();
  init.signal?.addEventListener('abort', stop);
  const limit =
    init.timeoutMs ??
    (init.body === undefined ? API_TIMEOUT_MS : typeof init.body === 'string' ? API_WRITE_TIMEOUT_MS : null);
  const timer = limit === null ? null : setTimeout(stop, limit);
  const response = await fetch(`${env.apiUrl}/api${path}`, {
    method: init.method ?? 'GET',
    headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: init.body,
    signal: abort.signal,
  }).finally(() => {
    if (timer) clearTimeout(timer);
    init.signal?.removeEventListener('abort', stop);
  });
  if (!response.ok) {
    const detail = await response.json().then(
      (b) => b?.detail,
      () => null,
    );
    throw new ApiError(response.status, typeof detail === 'string' ? detail : `Request failed (${response.status})`);
  }
  return response;
}

/** Fetch `path` (after /api) as JSON, with the current login's access token when there is one. */
export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; timeoutMs?: number } = {},
): Promise<T> {
  const response = await authedFetch(path, {
    method: init.method,
    timeoutMs: init.timeoutMs,
    headers: { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  return (response.status === 204 ? null : await response.json()) as T;
}
