import { useCallback, useEffect, useRef, useState } from 'react';

/** How long a press that finishes at once (a navigation, a toggle) ignores further taps. */
const TAP_COOLDOWN_MS = 400;

/**
 * Wraps a press handler so it can't run twice at once: taps while an async handler is still running
 * are dropped (`pending` is true meanwhile, for a spinner), and a sync handler ignores taps for a
 * moment, so a double tap can't open a screen twice or queue the same request twice.
 */
export function useGuardedPress<Args extends unknown[]>(
  onPress: ((...args: Args) => unknown) | undefined,
): { press: (...args: Args) => void; pending: boolean } {
  const busy = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const press = useCallback(
    (...args: Args) => {
      if (busy.current || !onPress) return;
      busy.current = true;
      let result: unknown;
      try {
        result = onPress(...args);
      } catch (error) {
        busy.current = false;
        throw error;
      }
      if (result instanceof Promise) {
        setPending(true);
        result
          .catch(() => {
            // The handler shows its own error; the guard only has to let go.
          })
          .finally(() => {
            busy.current = false;
            if (mounted.current) setPending(false);
          });
      } else {
        setTimeout(() => {
          busy.current = false;
        }, TAP_COOLDOWN_MS);
      }
    },
    [onPress],
  );

  return { press, pending };
}
