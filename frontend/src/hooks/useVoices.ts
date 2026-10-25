import { useCallback, useEffect, useState } from 'react';

import type { Status } from '@/components/Feedback';
import { usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { ApiError } from '@/services/api';
import { chooseVoice, readVoices, type Voice, type VoiceChoice } from '@/services/voice';

/** Why choosing a voice failed. */
function chooseError(e: unknown, name: string): string {
  if (e instanceof ApiError && e.status === 403)
    return `Only the account that set up the pillow can change the voice ${name} hears.`;
  if (e instanceof ApiError && e.status === 404) return "The pillow can't take changes from the app yet.";
  return "Couldn't save that. Check your connection and try again.";
}

export type Voices = {
  residentId: string | null;
  /** The voices, the one she hears and how it speaks; null while loading. */
  choice: VoiceChoice | null;
  failed: boolean;
  /** Whether this login set up the pillow, so may choose the voice and how it speaks. */
  isOwner: boolean;
  reload: () => void;
  /** Makes `voiceId` the voice she hears (optimistic), and says how that went. */
  choose: (voiceId: string) => Promise<Status | null>;
  /** Adds a voice just made (a clone or an accent copy) to the list without a reload. */
  add: (voice: Voice) => void;
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
  const [choice, setChoiceState] = useState<VoiceChoice | null>(null);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(() => {
    if (!residentId) return;
    readVoices(residentId, savedVoiceId).then(
      (next) => {
        setChoiceState(next);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, [residentId, savedVoiceId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const setChoice = useCallback((update: (c: VoiceChoice) => VoiceChoice) => {
    setChoiceState((c) => (c ? update(c) : c));
  }, []);

  const choose = useCallback(
    async (voiceId: string): Promise<Status | null> => {
      if (!residentId || !choice || !isOwner || choice.current === voiceId) return null;
      const before = choice.current;
      setChoice((c) => ({ ...c, current: voiceId }));
      try {
        const current = await chooseVoice(residentId, voiceId, choice.legacy ? (pillowId ?? undefined) : undefined);
        setChoice((c) => ({ ...c, current }));
        return { kind: 'saved', text: 'Saved' };
      } catch (e) {
        setChoice((c) => ({ ...c, current: before }));
        return { kind: 'error', text: chooseError(e, name) };
      }
    },
    [residentId, choice, isOwner, pillowId, name, setChoice],
  );

  const add = useCallback(
    (voice: Voice) =>
      setChoice((c) => (c.voices.some((v) => v.id === voice.id) ? c : { ...c, voices: [...c.voices, voice] })),
    [setChoice],
  );

  return { residentId, choice, failed, isOwner, reload, choose, add, setChoice };
}
