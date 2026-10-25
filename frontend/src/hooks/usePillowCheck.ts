import { useEffect, useState } from 'react';

import { PING_EVERY_MS } from '@/constants/pillow';
import { usePillow } from '@/hooks/usePillow';
import { type PillowPing, pingPillow } from '@/services/ping';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * While the pillow is offline, ping it every `PING_EVERY_MS` and say which part answered, so the
 * offline card can tell "nothing answers" from "the speaker doesn't". When the sensors answer again
 * the pillow's data is read at once instead of waiting for the next update. Null while online.
 */
export function usePillowCheck(pillowId: string | null, offline: boolean): PillowPing | null {
  const { refresh } = usePillow();
  // Whose answer it is, so switching person never shows the last pillow's answer.
  const [ping, setPing] = useState<{ pillowId: string; answer: PillowPing } | null>(null);

  useEffect(() => {
    if (!offline || !pillowId) return;
    let stopped = false;
    (async () => {
      while (!stopped) {
        try {
          const answer = await pingPillow(pillowId);
          if (stopped) return;
          setPing({ pillowId, answer });
          if (answer.node_alive) await refresh();
        } catch {
          // Can't reach the backend: keep the last answer and try again next round
        }
        await wait(PING_EVERY_MS);
      }
    })();
    return () => {
      stopped = true;
    };
  }, [pillowId, offline, refresh]);

  return offline && ping?.pillowId === pillowId ? ping.answer : null;
}
