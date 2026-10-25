/** Calls to the FastAPI backend, signed with the app's Supabase login (never an agent token). */

import { env } from '@/config/env';
import { supabase } from '@/services/supabase/client';

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
 * (JSON, a recording to upload) and any answer (JSON, audio). Throws an ApiError for a non-2xx answer.
 */
export async function authedFetch(
  path: string,
  init: { method?: string; headers?: Record<string, string>; body?: BodyInit } = {},
): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const response = await fetch(`${env.apiUrl}/api${path}`, {
    method: init.method ?? 'GET',
    headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: init.body,
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
export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await authedFetch(path, {
    method: init.method,
    headers: { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  return (response.status === 204 ? null : await response.json()) as T;
}
