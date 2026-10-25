import { memo } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { PlayButton } from '@/components/PlayButton';
import { CheckIcon } from '@/components/TabIcons';
import { useTheme } from '@/hooks/useTheme';
import { dayMonth } from '@/services/schedule';
import type { Voice } from '@/services/voice';

/** Who made a family voice or accent copy and when, as a sentence. */
export function madeBy(voice: Voice): string {
  const who = voice.created_by_name ?? 'someone in the family';
  return `Made by ${who}${voice.created_at ? ` on ${dayMonth(voice.created_at.slice(0, 10))}` : ''}.`;
}

type VoiceRowProps = {
  voice: Voice;
  /** Her preferred name. */
  name: string;
  selected: boolean;
  /** Whether this login may choose it (the owner); others only listen. */
  canChoose: boolean;
  /** Its sample's phase; undefined when samples aren't available. */
  playing: 'loading' | 'playing' | null | undefined;
  onChoose: (id: string) => unknown;
  onPlay: (voice: Voice) => void;
  onRemove?: (voice: Voice) => void;
};

/**
 * One voice: a round check and "In use" on the one she hears, Play on the right. For the owner,
 * tapping the name chooses it; everyone else sees no check and only listens, so nothing can be
 * tapped that would then be refused. "In use" sits on the name's line, so a row never changes size.
 */
export const VoiceRow = memo(function VoiceRow({
  voice,
  name,
  selected,
  canChoose,
  playing,
  onChoose,
  onPlay,
  onRemove,
}: VoiceRowProps) {
  const { colors } = useTheme();
  const meta = voice.source === 'stock' ? voice.description : madeBy(voice);
  const label = (
    <View className="flex-1 gap-0.5">
      <View className="flex-row flex-wrap items-baseline gap-x-2">
        <Text className="font-sans-semibold text-base text-ink">{voice.name}</Text>
        {selected ? <Text className="font-sans-semibold text-[13px] text-accent-text">In use</Text> : null}
      </View>
      {meta ? <Text className="font-sans text-[13px] text-ink-muted">{meta}</Text> : null}
    </View>
  );
  return (
    <View
      className={`rounded-2xl bg-surface ${selected ? 'border-[1.5px] border-accent' : 'border-[1.5px] border-transparent'}`}
    >
      <View className="flex-row items-center gap-2 py-1.5 pl-1.5 pr-2.5">
        {canChoose ? (
          <Pressable
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={`${voice.name}${meta ? `. ${meta}` : ''}`}
            accessibilityHint={!selected ? `Makes this the voice ${name} hears` : undefined}
            onPress={() => onChoose(voice.id)}
            className="min-h-14 flex-1 flex-row items-center gap-3 rounded-xl px-2 py-2 active:opacity-80"
          >
            <View
              className={`size-6 items-center justify-center rounded-full border-[1.5px] ${
                selected ? 'border-accent bg-accent' : 'border-hairline'
              }`}
            >
              {selected ? <CheckIcon color={colors['on-accent']} size={14} /> : null}
            </View>
            {label}
          </Pressable>
        ) : (
          <View accessible className="min-h-14 flex-1 flex-row items-center px-2 py-2">
            {label}
          </View>
        )}
        {playing !== undefined ? <PlayButton what={voice.name} state={playing} onPress={() => onPlay(voice)} /> : null}
      </View>
      {onRemove ? (
        <View className="flex-row justify-end px-1 pb-1">
          <Button variant="ghost" title="Remove" onPress={() => onRemove(voice)} />
        </View>
      ) : null}
    </View>
  );
});
