import { useEffect, useRef, useState } from 'react';

import { SKELETON_DELAY, SKELETON_MIN_SHOWN } from '@/constants/motion';

/**
 * Whether to show a skeleton for `loading`: not at all if the data lands within the delay, and
 * once shown, for at least the minimum time, so it never flickers.
 */
export function useDelayedLoading(loading: boolean, delay = SKELETON_DELAY, minShown = SKELETON_MIN_SHOWN): boolean {
  const [show, setShow] = useState(false);
  const shownAt = useRef<number | null>(null);

  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => {
        shownAt.current = Date.now();
        setShow(true);
      }, delay);
      return () => clearTimeout(timer);
    }
    if (shownAt.current === null) return;
    const timer = setTimeout(
      () => {
        shownAt.current = null;
        setShow(false);
      },
      Math.max(0, minShown - (Date.now() - shownAt.current)),
    );
    return () => clearTimeout(timer);
  }, [loading, delay, minShown]);

  return show;
}
