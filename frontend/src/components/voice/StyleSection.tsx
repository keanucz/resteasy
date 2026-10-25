import { useMemo, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { type Status, StatusLine } from '@/components/Feedback';
import { phaseOf, PlayButton, previewError } from '@/components/PlayButton';
import { SegmentedTabs } from '@/components/Selection';
import { TextField } from '@/components/TextField';
import { Disclosure } from '@/components/voice/Disclosure';
import { RadioList } from '@/components/voice/RadioList';
import { loadOnce, type VoicePlayer } from '@/hooks/useVoicePlayer';
import { ApiError } from '@/services/api';
import { forgetPreviews, PREVIEW_MAX, previewVoice, saveStyle, type VoiceStyle } from '@/services/voice';

/** Speed steps, from Cartesia's 0.6 to 1.5; the pillow has always spoken at Calm. */
const SPEEDS = [
  { value: '0.7', label: 'Slower' },
  { value: '0.85', label: 'Calm' },
  { value: '1', label: 'Usual' },
  { value: '1.15', label: 'Brisker' },
] as const;

/** Volume steps, from Cartesia's 0.5 to 2. */
const VOLUMES = [
  { value: '0.8', label: 'Softer' },
  { value: '1', label: 'Usual' },
  { value: '1.3', label: 'Louder' },
] as const;

/** How each tone the backend offers sounds, in a few words. */
const TONES: Record<string, { label: string; meta: string }> = {
  calm: { label: 'Calm', meta: 'Even and unhurried, for the middle of the night' },
  peaceful: { label: 'Peaceful', meta: 'Soft and settling' },
  content: { label: 'Content', meta: 'Relaxed and easy-going' },
  affectionate: { label: 'Affectionate', meta: 'Warm, like family' },
  sympathetic: { label: 'Sympathetic', meta: 'Gentle and understanding' },
  neutral: { label: 'Plain', meta: 'No particular feeling' },
  happy: { label: 'Cheerful', meta: 'Bright, for daytime reminders' },
};

/** The step nearest a saved value, so a value set elsewhere still shows a step. */
function nearest<T extends string>(steps: readonly { value: T }[], value: number): T {
  return steps.reduce((best, step) =>
    Math.abs(Number(step.value) - value) < Math.abs(Number(best.value) - value) ? step : best,
  ).value;
}

const label = (steps: readonly { value: string; label: string }[], value: string) =>
  steps.find((s) => s.value === value)?.label.toLowerCase() ?? value;

type StyleSectionProps = {
  residentId: string;
  name: string;
  /** The voice she hears, which "Hear it" speaks in. */
  voiceId: string;
  saved: VoiceStyle;
  emotions: string[];
  isOwner: boolean;
  /** The language "Hear it" speaks in (a typed line is translated first). */
  language: string;
  player: VoicePlayer;
  onSaved: (style: VoiceStyle) => void;
};

/**
 * How the pillow speaks: speed, volume and tone. Try it in her voice before saving; only the
 * owner saves, everyone else sees it in words (the page says why, once, under its title).
 */
export function StyleSection({
  residentId,
  name,
  voiceId,
  saved,
  emotions,
  isOwner,
  language,
  player,
  onSaved,
}: StyleSectionProps) {
  const [speed, setSpeed] = useState(nearest(SPEEDS, saved.speed));
  const [volume, setVolume] = useState(nearest(VOLUMES, saved.volume));
  const [emotion, setEmotion] = useState(saved.emotion);
  const [line, setLine] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const draft: VoiceStyle = { speed: Number(speed), volume: Number(volume), emotion };
  // Only the chosen tone says how it sounds, so the list stays short.
  const tones = useMemo(
    () => emotions.map((e) => ({ value: e, label: TONES[e]?.label ?? e, meta: e === emotion ? TONES[e]?.meta : undefined })),
    [emotions, emotion],
  );
  const changed =
    speed !== nearest(SPEEDS, saved.speed) || volume !== nearest(VOLUMES, saved.volume) || emotion !== saved.emotion;
  const fallbackLine = `Goodnight ${name}, the light is on to help you find your way.`;

  const hear = () => {
    const text = line || fallbackLine;
    setStatus(null);
    player
      .toggle('style', () =>
        loadOnce(`preview|${residentId}|${voiceId}|${text}|${JSON.stringify(draft)}|${language}`, () =>
          previewVoice(residentId, voiceId, text, draft, language),
        ),
      )
      .catch((e) => setStatus({ kind: 'error', text: previewError(e) }));
  };

  const save = async () => {
    setBusy(true);
    setStatus(null);
    try {
      onSaved(await saveStyle(residentId, draft));
      forgetPreviews();
      setStatus({ kind: 'saved', text: `Saved. The pillow speaks to ${name} like this from now on.` });
    } catch (e) {
      setStatus({
        kind: 'error',
        text:
          e instanceof ApiError && e.status === 403
            ? 'Only the account that set up the pillow can change this.'
            : "Couldn't save that. Check your connection and try again.",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <View className="gap-4">
      {isOwner ? (
        <>
          <View className="gap-2">
            <Text className="font-sans-semibold text-sm text-ink-muted">Speed</Text>
            <SegmentedTabs options={SPEEDS} value={speed} onChange={setSpeed} />
          </View>
          <View className="gap-2">
            <Text className="font-sans-semibold text-sm text-ink-muted">Volume</Text>
            <SegmentedTabs options={VOLUMES} value={volume} onChange={setVolume} />
          </View>
          <Disclosure title="Tone" value={TONES[emotion]?.label ?? emotion}>
            <Text className="font-sans text-[13px] text-ink-muted">Tone works in English only.</Text>
            <RadioList
              label="Tone"
              options={tones}
              value={emotion}
              onChange={setEmotion}
            />
          </Disclosure>
        </>
      ) : (
        <Text className="font-sans text-base text-ink">
          The pillow speaks at a {label(SPEEDS, nearest(SPEEDS, saved.speed))} speed and{' '}
          {label(VOLUMES, nearest(VOLUMES, saved.volume))} volume, in a{' '}
          {(TONES[saved.emotion]?.label ?? saved.emotion).toLowerCase()} tone.
        </Text>
      )}

      <View className="gap-2">
        <TextField
          label="Try it with your own words"
          value={line}
          onChangeText={setLine}
          placeholder={fallbackLine}
          maxLength={PREVIEW_MAX}
          returnKeyType="done"
        />
        <PlayButton
          fullWidth
          title="Hear it"
          what={isOwner ? 'these settings' : 'the pillow'}
          state={phaseOf(player.playing, 'style')}
          onPress={hear}
        />
      </View>

      {isOwner ? (
        <Button
          fullWidth
          title="Save how it speaks"
          loading={busy}
          disabled={!changed}
          onPress={save}
        />
      ) : null}
      <StatusLine status={status} />
    </View>
  );
}
