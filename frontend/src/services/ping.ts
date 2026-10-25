/** POST /api/pillows/{id}/ping: whether the pillow's two boards are answering right now. */

import { api } from '@/services/api';

/**
 * The ping's answer. `node_alive`: the sensors inside the pillow sent a report in the last moments.
 * `voice_unit_alive`: that report came through the bedside speaker unit too. `active`: both did.
 */
export type PillowPing = {
  active: boolean;
  node_alive: boolean;
  voice_unit_alive: boolean;
  link: 'hotspot' | 'ble' | 'usb' | null;
  last_seen_at: string | null;
};

/** Ping the pillow; the backend waits up to ~4 s for a fresh report before saying it's silent. */
export function pingPillow(pillowId: string): Promise<PillowPing> {
  return api<PillowPing>(`/pillows/${encodeURIComponent(pillowId)}/ping`, { method: 'POST' });
}
