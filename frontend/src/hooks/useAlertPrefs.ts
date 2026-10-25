import { useFocusEffect } from 'expo-router';
import { useCallback, useSyncExternalStore } from 'react';

import { type AlertPrefs, getAlertPrefs } from '@/services/alerts';

/** The signed-in contact's alert settings, shared by Settings and Tonight, so a change shows on both. */
let current: { contactId: string; prefs: AlertPrefs } | null = null;
const listeners = new Set<() => void>();

/** Records the contact's alert settings (after a read or a save) and tells every screen showing them. */
export function setAlertPrefs(contactId: string, prefs: AlertPrefs) {
  current = { contactId, prefs };
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** The contact's alert settings, read again each time the screen comes into view; null until known. */
export function useAlertPrefs(contactId: string | null): AlertPrefs | null {
  const read = useCallback(() => (current && current.contactId === contactId ? current.prefs : null), [contactId]);
  const prefs = useSyncExternalStore(subscribe, read, read);
  useFocusEffect(
    useCallback(() => {
      if (!contactId) return;
      getAlertPrefs().then(
        (p) => setAlertPrefs(contactId, p),
        () => {
          // Unreadable for now: the screens keep what they had (or the defaults).
        },
      );
    }, [contactId]),
  );
  return prefs;
}
