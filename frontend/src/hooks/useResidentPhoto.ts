import { useCallback, useEffect, useSyncExternalStore } from 'react';

import { photoUrl } from '@/services/photo';

/** Photo links by resident, shared by every screen, so a new upload shows everywhere at once. */
const urls = new Map<string, string | null>();
const listeners = new Set<() => void>();

/** Records a resident's new photo link (after an upload) and tells every screen showing it. */
export function setResidentPhoto(residentId: string, url: string | null) {
  urls.set(residentId, url);
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** The resident's photo link, or null when they have none (initials show instead). */
export function useResidentPhoto(residentId: string | null): string | null {
  const read = useCallback(() => (residentId ? (urls.get(residentId) ?? null) : null), [residentId]);
  const url = useSyncExternalStore(subscribe, read, read);
  useEffect(() => {
    if (!residentId || urls.has(residentId)) return;
    photoUrl(residentId).then(
      (u) => setResidentPhoto(residentId, u),
      () => setResidentPhoto(residentId, null),
    );
  }, [residentId]);
  return url;
}
