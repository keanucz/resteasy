/** Calls to the backend's connection-test router. */

import { apiRequest } from '@/services/api/client';

export type ConnectionTestResponse = {
  message: string;
  host: string;
  server_time: string;
};

/** Fetch GET /api/test to confirm the app can reach the backend. */
export function testConnection(): Promise<ConnectionTestResponse> {
  return apiRequest<ConnectionTestResponse>('/test');
}
