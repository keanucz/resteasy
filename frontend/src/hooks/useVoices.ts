import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

import type { Status } from '@/components/Feedback';
import { usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { ApiError } from '@/services/api';
import { chooseVoice, readVoices, saveLanguage, type Voice, type VoiceChoice } from '@/services/voice';

/** Why choosing a voice failed. */
function chooseError(e: unknown, name: string): string {
  if (e instanceof ApiError && e.status === 403)
    return `Only the account that set up the pillow can change the voice ${name} hears.`;
  if (e instanceof ApiError && e.status === 404) return "The pillow can't take changes from the app yet.";
  return "Couldn't save that. Check your connection and try again.";
}

/** How long a read voice list counts as fresh, so going between Settings and Custom voice doesn't read it again. */
const FRESH_MS = 30_000;

// The voice list per resident, shared by Settings and the Custom voice page so each shows the
// other's changes and opens with what is already known.
const cache = new Map<string, { choice: VoiceChoice; at: number }>();
const listeners = new Set<() => void>();
const reading = new Map<string, Promise<VoiceChoice>>();

/**
 * The voice being saved per resident: `wanted` is the newest tap, `confirmed` what the backend
 * last said. Only one save runs at a time; taps meanwhile just move `wanted`.
 */
type Save = { busy: boolean; wanted: string; confirmed: string };
const saves = new Map<string, Save>();

/** Keeps `choice` for `residentId` and tells every screen showing it; `fresh` when it just came from the backend. */
function publish(residentId: string, choice: VoiceChoice, fresh = false) {
  const at = fresh ? Date.now() : (cache.get(residentId)?.at ?? 0);
  cache.set(residentId, { choice, at });
  listeners.forEach((l) => l());
}

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

/** One read of the voice list per resident at a time, shared by every screen asking. */
function read(residentId: string, savedVoiceId: string | undefined): Promise<VoiceChoice> {
  const running = reading.get(residentId);
  if (running) return running;
  const next = readVoices(residentId, savedVoiceId).finally(() => reading.delete(residentId));
  reading.set(residentId, next);
  return next;
}

export type Voices = {
  residentId: string | null;
  /** The voices, the one she hears and how it speaks; null while loading. */
  choice: VoiceChoice | null;
  failed: boolean;
  /** Whether this login set up the pillow, so may choose the voice and how it speaks. */
  isOwner: boolean;
  /** Reads the list again; settles when it has arrived (or failed). */
  reload: () => Promise<void>;
  /**
   * Makes `voiceId` the voice she hears (optimistic), and says how that went. Quick taps send at
   * most one save at a time, the newest choice last; the taps it replaced answer null.
   */
  choose: (voiceId: string) => Promise<Status | null>;
  /** Adds a voice just made (a clone or an accent copy) to the list without a reload. */
  add: (voice: Voice) => void;
  /** Switches the previews to `language` at once (optimistic), and says how saving it went. */
  setLanguage: (language: string) => Promise<Status | null>;
  setChoice: (update: (choice: VoiceChoice) => VoiceChoice) => void;
};

/**
 * The voice list for the pillow on screen: loads it, chooses a voice, and knows whether this
 * login is the owner. Used by Settings' voice section and the Custom voice page.
 */
export function useVoices(name: string): Voices {
  const { resident } = usePillow();
  const { pillowId, people } = usePillowLink();
  const residentId = resident?.id ?? null;
  const savedVoiceId = resident?.voice_id;
  const isOwner = people.some((p) => p.pillow_id === pillowId && p.role === 'owner');
  const choice = useSyncExternalStore(subscribe, () => (residentId ? (cache.get(residentId)?.choice ?? null) : null));
  const [failedFor, setFailedFor] = useState<string | null>(null);
  // Only the older backend needs this (to know the voice in use), so a new value doesn't mean a new read.
  const savedVoice = useRef(savedVoiceId);

  useEffect(() => {
    savedVoice.current = savedVoiceId;
  }, [savedVoiceId]);

  const load = useCallback(
    (force: boolean): Promise<void> => {
      if (!residentId) return Promise.resolve();
      const known = cache.get(residentId);
      if (!force && known && Date.now() - known.at < FRESH_MS) return Promise.resolve();
      return read(residentId, savedVoice.current).then(
        (next) => {
          const save = saves.get(residentId);
          // A choice still being saved wins over a list read before it went out.
          publish(residentId, save?.busy ? { ...next, current: save.wanted } : next, true);
          setFailedFor((f) => (f === residentId ? null : f));
        },
        () => setFailedFor(residentId),
      );
    },
    [residentId],
  );

  useEffect(() => {
    load(false);
  }, [load]);

  const reload = useCallback(() => load(true), [load]);

  const setChoice = useCallback(
    (update: (c: VoiceChoice) => VoiceChoice) => {
      const known = residentId ? cache.get(residentId)?.choice : undefined;
      if (residentId && known) publish(residentId, update(known));
    },
    [residentId],
  );

  const choose = useCallback(
    async (voiceId: string): Promise<Status | null> => {
      const shown = residentId ? cache.get(residentId)?.choice : undefined;
      if (!residentId || !shown || !isOwner || shown.current === voiceId) return null;
      const save = saves.get(residentId) ?? { busy: false, wanted: shown.current, confirmed: shown.current };
      saves.set(residentId, save);
      if (!save.busy) save.confirmed = shown.current;
      save.wanted = voiceId;
      setChoice((c) => ({ ...c, current: voiceId }));
      // The save already running sends this newer choice when it is done.
      if (save.busy) return null;
      save.busy = true;
      const legacyPillowId = shown.legacy ? (pillowId ?? undefined) : undefined;
      try {
        for (;;) {
          const target = save.wanted;
          // Tapped back to what the backend already has while the last save was out.
          if (target === save.confirmed) return null;
          try {
            save.confirmed = await chooseVoice(residentId, target, legacyPillowId);
            if (save.wanted === target) {
              setChoice((c) => ({ ...c, current: save.confirmed }));
              return { kind: 'saved', text: 'Saved' };
            }
          } catch (e) {
            if (save.wanted === target) {
              setChoice((c) => ({ ...c, current: save.confirmed }));
              return { kind: 'error', text: chooseError(e, name) };
            }
          }
        }
      } finally {
        save.busy = false;
      }
    },
    [residentId, isOwner, pillowId, name, setChoice],
  );

  const add = useCallback(
    (voice: Voice) =>
      setChoice((c) => (c.voices.some((v) => v.id === voice.id) ? c : { ...c, voices: [...c.voices, voice] })),
    [setChoice],
  );

  const setLanguage = useCallback(
    async (language: string): Promise<Status | null> => {
      const shown = residentId ? cache.get(residentId)?.choice : undefined;
      if (!residentId || !shown || shown.language === language) return null;
      const before = shown.language;
      setChoice((c) => ({ ...c, language }));
      try {
        await saveLanguage(residentId, language);
        return null;
      } catch (e) {
        setChoice((c) => (c.language === language ? { ...c, language: before } : c));
        return { kind: 'error', text: chooseError(e, name) };
      }
    },
    [residentId, name, setChoice],
  );

  const failed = failedFor !== null && failedFor === residentId && !choice;
  return { residentId, choice, failed, isOwner, reload, choose, add, setChoice, setLanguage };
}
