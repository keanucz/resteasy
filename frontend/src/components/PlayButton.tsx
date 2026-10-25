import { memo } from 'react';
import { ActivityIndicator, Pressable, Text } from 'react-native';

import { PlayIcon, StopIcon } from '@/components/TabIcons';
import type { Playing } from '@/hooks/useVoicePlayer';
import { useTheme } from '@/hooks/useTheme';
import { ApiError } from '@/services/api';

/** Why playing a voice failed, in words. */
export function previewError(e: unknown): string {
  if (e instanceof ApiError && e.status === 404) return "The pillow can't play voices to the app yet.";
  return "Couldn't play that voice. Check your connection and try again.";
}

type PlayButtonProps = {
  /** What it plays, for screen readers ("Ava", "your recording"). */
  what: string;
  /** This button's sound, if it is the one loading or playing. */
  state: 'loading' | 'playing' | null;
  onPress: () => void;
  title?: string;
  fullWidth?: boolean;
};

/**
 * Play, and Stop while its sound is loading or playing: the fill turns solid and the label says
 * Stop, so which voice is sounding is plain at a glance. Same width either way, so nothing moves.
 */
export const PlayButton = memo(function PlayButton({
  what,
  state,
  onPress,
  title = 'Play',
  fullWidth = false,
}: PlayButtonProps) {
  const { colors } = useTheme();
  const on = state !== null;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={on ? `Stop ${what}` : `${title}, ${what}`}
      accessibilityState={{ busy: state === 'loading' }}
      onPress={onPress}
      className={`h-11 flex-row items-center justify-center gap-1.5 rounded-xl px-3.5 active:opacity-80 ${
        on ? 'bg-accent' : 'bg-accent/25'
      } ${fullWidth ? 'self-stretch' : 'w-[92px]'}`}
    >
      {state === 'loading' ? (
        <ActivityIndicator size="small" color={colors['on-accent']} />
      ) : on ? (
        <StopIcon color={colors['on-accent']} size={16} />
      ) : (
        <PlayIcon color={colors.ink} size={16} />
      )}
      <Text className={`font-sans-semibold text-base ${on ? 'text-on-accent' : 'text-ink'}`}>
        {on ? 'Stop' : title}
      </Text>
    </Pressable>
  );
});

/** The phase of `key`'s sound on the shared player, or null when something else (or nothing) is playing. */
export const phaseOf = (playing: Playing, key: string) => (playing?.key === key ? playing.phase : null);
