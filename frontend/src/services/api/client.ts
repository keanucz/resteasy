/** Single fetch wrapper for talking to the FastAPI backend. Feature modules build on this. */

import { env } from '@/config/env';

const API_PREFIX = '/api';

/** Thrown by apiRequest on non-2xx responses; `status` is the HTTP code and `message` the raw response body. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Send a JSON request to `path` (relative to /api) and return the parsed body.
 * Resolves to undefined when the body is empty; throws ApiError on any non-2xx response.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(`${env.apiUrl}${API_PREFIX}${path}`, { ...init, headers });
  const body = await response.text();

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }

  return (body ? JSON.parse(body) : undefined) as T;
}
