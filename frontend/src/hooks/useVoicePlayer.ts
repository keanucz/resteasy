import { setAudioModeAsync, useAudioPlayer } from 'expo-audio';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/** What is sounding: `key` names the thing playing (a voice id, "recording"), loading while its audio is fetched. */
export type Playing = { key: string; phase: 'loading' | 'playing' } | null;

export type VoicePlayer = {
  playing: Playing;
  /** Plays what `load` gives back under `key`; pressing the same key again stops it. Throws if loading fails. */
  toggle: (key: string, load: () => Promise<string>) => Promise<void>;
  stop: () => void;
};

// Audio still being fetched, by what it is, so asking again before it arrives doesn't fetch (or pay for) it twice.
const loads = new Map<string, Promise<string>>();

/**
 * Runs `load` once for `id` at a time: a second ask while the first is still out gets the same
 * answer. `id` must say everything that changes the audio (voice, words, style).
 */
export function loadOnce(id: string, load: () => Promise<string>): Promise<string> {
  const running = loads.get(id);
  if (running) return running;
  const next = load().finally(() => loads.delete(id));
  loads.set(id, next);
  return next;
}

/**
 * One player for every Play button on a screen, so only one voice sounds at a time and each
 * button can say whether it is the one playing. Plays even with the phone's silent switch on,
 * since a family member pressing Play wants to hear it.
 */
export function useVoicePlayer(): VoicePlayer {
  const player = useAudioPlayer(null);
  const [playing, setPlaying] = useState<Playing>(null);
  // The same as `playing`, read by toggle so it stays one function while sounds come and go.
  const playingRef = useRef<Playing>(null);
  // Bumped on every start and stop, so a preview that arrives late doesn't play over a newer choice.
  const turn = useRef(0);
  // Set once the current sound has really started, so the pause before it starts isn't read as its end.
  const started = useRef(false);

  const show = useCallback((next: Playing) => {
    playingRef.current = next;
    setPlaying(next);
  }, []);

  useEffect(() => {
    const sub = player.addListener('playbackStatusUpdate', (status) => {
      if (status.playing) started.current = true;
      else if (started.current) {
        started.current = false;
        show(null);
      }
    });
    return () => sub.remove();
  }, [player, show]);

  const stop = useCallback(() => {
    turn.current++;
    started.current = false;
    player.pause();
    show(null);
  }, [player, show]);

  const toggle = useCallback(
    async (key: string, load: () => Promise<string>) => {
      if (playingRef.current?.key === key) return stop();
      const mine = ++turn.current;
      started.current = false;
      player.pause();
      show({ key, phase: 'loading' });
      try {
        const uri = await load();
        if (mine !== turn.current) return;
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false }).catch(() => {});
        if (mine !== turn.current) return;
        player.replace({ uri });
        player.play();
        show({ key, phase: 'playing' });
      } catch (e) {
        if (mine === turn.current) show(null);
        throw e;
      }
    },
    [player, show, stop],
  );

  return useMemo(() => ({ playing, toggle, stop }), [playing, toggle, stop]);
}
