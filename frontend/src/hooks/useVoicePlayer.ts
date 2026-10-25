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

/**
 * One player for every Play button on a screen, so only one voice sounds at a time and each
 * button can say whether it is the one playing. Plays even with the phone's silent switch on,
 * since a family member pressing Play wants to hear it.
 */
export function useVoicePlayer(): VoicePlayer {
  const player = useAudioPlayer(null);
  const [playing, setPlaying] = useState<Playing>(null);
  // Bumped on every start and stop, so a preview that arrives late doesn't play over a newer choice.
  const turn = useRef(0);
  // Set once the current sound has really started, so the pause before it starts isn't read as its end.
  const started = useRef(false);

  useEffect(() => {
    const sub = player.addListener('playbackStatusUpdate', (status) => {
      if (status.playing) started.current = true;
      else if (started.current) {
        started.current = false;
        setPlaying(null);
      }
    });
    return () => sub.remove();
  }, [player]);

  const stop = useCallback(() => {
    turn.current++;
    started.current = false;
    player.pause();
    setPlaying(null);
  }, [player]);

  const toggle = useCallback(
    async (key: string, load: () => Promise<string>) => {
      if (playing?.key === key) return stop();
      const mine = ++turn.current;
      started.current = false;
      player.pause();
      setPlaying({ key, phase: 'loading' });
      try {
        const uri = await load();
        if (mine !== turn.current) return;
        await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: false }).catch(() => {});
        player.replace({ uri });
        player.play();
        setPlaying({ key, phase: 'playing' });
      } catch (e) {
        if (mine === turn.current) setPlaying(null);
        throw e;
      }
    },
    [player, playing?.key, stop],
  );

  return useMemo(() => ({ playing, toggle, stop }), [playing, toggle, stop]);
}
