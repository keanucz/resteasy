import { router } from 'expo-router';
import { memo, useCallback, useMemo, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { type Status, StatusLine } from '@/components/Feedback';
import { ListRow } from '@/components/List';
import { phaseOf, previewError } from '@/components/PlayButton';
import { OptionSelect } from '@/components/OptionSelect';
import { ListRowSkeleton, SkeletonGroup } from '@/components/Skeleton';
import { ChevronIcon } from '@/components/TabIcons';
import { VoiceRow } from '@/components/voice/VoiceRow';
import { useGuardedPress } from '@/hooks/useGuardedPress';
import { useTheme } from '@/hooks/useTheme';
import { loadOnce, useVoicePlayer } from '@/hooks/useVoicePlayer';
import { useVoices } from '@/hooks/useVoices';
import { sampleUri, type Voice } from '@/services/voice';

/**
 * Settings' voice section: which voice she hears now, and every voice with Play to hear its
 * ready-made sample (instant, no voice service call). The owner taps a voice to choose it.
 * Family voices, accents, how it speaks and names it should say right live on the Custom voice page.
 */
export const VoicePicker = memo(function VoicePicker({ name }: { name: string }) {
  const { colors } = useTheme();
  const { residentId, choice, failed, isOwner, reload, choose, setLanguage } = useVoices(name);
  const language = choice?.language ?? 'en';
  const { playing, toggle, stop } = useVoicePlayer();
  const [status, setStatus] = useState<Status | null>(null);

  const play = useCallback(
    (voice: Voice) => {
      if (!residentId) return;
      setStatus(null);
      toggle(voice.id, () => loadOnce(`sample|${language}|${voice.id}`, () => sampleUri(residentId, voice, language))).catch(
        (e) => setStatus({ kind: 'error', text: previewError(e) }),
      );
    },
    [residentId, toggle, language],
  );

  const changeLanguage = useCallback(
    async (code: string) => {
      stop();
      setStatus(null);
      setStatus(await setLanguage(code));
    },
    [setLanguage, stop],
  );

  const languageOptions = useMemo(
    () => choice?.languages.map((l) => ({ value: l.code, label: l.name })) ?? [],
    [choice?.languages],
  );

  const pick = useCallback(
    async (voiceId: string) => {
      setStatus(null);
      setStatus(await choose(voiceId));
    },
    [choose],
  );

  // A double tap opens the page once.
  const openCustom = useGuardedPress(() => {
    stop();
    router.push('/voice');
  });

  const { current, stock, own } = useMemo(
    () => ({
      current: choice?.voices.find((v) => v.id === choice.current),
      stock: choice?.voices.filter((v) => v.source === 'stock') ?? [],
      own: choice?.voices.filter((v) => v.source !== 'stock') ?? [],
    }),
    [choice],
  );

  if (failed) {
    return (
      <View className="items-start gap-2">
        <Text className="font-sans text-base text-ink-muted">
          Couldn&apos;t load the voices. Check your connection and try again.
        </Text>
        <Button variant="ghost" title="Try again" onPress={reload} />
      </View>
    );
  }

  if (!choice) {
    // Holds the list's place while voices load, so nothing below jumps when they arrive.
    return (
      <SkeletonGroup>
        <View className="gap-2.5">
          <ListRowSkeleton />
          <ListRowSkeleton />
          <ListRowSkeleton />
        </View>
      </SkeletonGroup>
    );
  }

  const row = (voice: Voice) => (
    <VoiceRow
      key={voice.id}
      voice={voice}
      name={name}
      selected={voice.id === choice.current}
      canChoose={isOwner}
      playing={choice.legacy ? undefined : phaseOf(playing, voice.id)}
      onChoose={pick}
      onPlay={play}
    />
  );

  return (
    <View className="gap-3">
      <Text className="font-sans text-base text-ink">
        {current ? (
          <>
            {name} hears <Text className="font-sans-semibold">{current.name}</Text> now.
          </>
        ) : (
          `Choose the voice ${name} hears.`
        )}
      </Text>

      {languageOptions.length > 1 ? (
        <OptionSelect
          label="Preview language"
          value={language}
          options={languageOptions}
          onChange={changeLanguage}
          disabled={!isOwner}
        />
      ) : null}

      {choice.voices.length === 0 ? (
        <Text className="font-sans text-base text-ink-muted">Voice choices arrive with the next pillow update.</Text>
      ) : (
        <View accessibilityRole="radiogroup" accessibilityLabel="Voice" className="gap-2.5">
          {stock.map(row)}
        </View>
      )}

      {own.length ? (
        <View className="gap-2.5 pt-2">
          <Text accessibilityRole="header" className="font-sans-semibold text-sm text-ink-muted">
            Family voices
          </Text>
          {own.map(row)}
        </View>
      ) : null}

      <StatusLine status={status} />

      {!isOwner ? (
        <Text className="font-sans text-sm text-ink-muted">
          Only the account that set up the pillow can change the voice {name} hears. You can listen to each one.
        </Text>
      ) : null}

      {choice.legacy ? (
        <Text className="font-sans text-sm text-ink-muted">
          Hearing a voice first isn&apos;t available on this pillow yet.
        </Text>
      ) : (
        <ListRow
          title="Custom voice"
          meta="Family voices, speed and tone, names to say right, accents."
          trailing={<ChevronIcon color={colors['ink-muted']} />}
          onPress={openCustom.press}
        />
      )}
    </View>
  );
});
