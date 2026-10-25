import { useCallback, useEffect, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { CloneVoiceSheet } from '@/components/CloneVoiceSheet';
import { Dialog, type Status, StatusLine } from '@/components/Feedback';
import { phaseOf, PlayButton, previewError } from '@/components/PlayButton';
import { ListRowSkeleton, SkeletonGroup } from '@/components/Skeleton';
import { CheckIcon, MicIcon } from '@/components/TabIcons';
import { TextField } from '@/components/TextField';
import { usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useVoicePlayer } from '@/hooks/useVoicePlayer';
import { useTheme } from '@/hooks/useTheme';
import { ApiError } from '@/services/api';
import { dayMonth } from '@/services/schedule';
import {
  chooseVoice,
  deleteClone,
  PREVIEW_MAX,
  previewVoice,
  readVoices,
  type Voice,
  type VoiceChoice,
} from '@/services/voice';

/** Who made a family voice and when, as a sentence. */
function madeBy(voice: Voice): string {
  const who = voice.created_by_name ?? 'someone in the family';
  return `Made by ${who}${voice.created_at ? ` on ${dayMonth(voice.created_at.slice(0, 10))}` : ''}.`;
}

/** Why choosing a voice failed. */
function chooseError(e: unknown, name: string): string {
  if (e instanceof ApiError && e.status === 403)
    return `You're not in ${name}'s care circle, so you can't change the voice.`;
  if (e instanceof ApiError && e.status === 404) return "The pillow can't take changes from the app yet.";
  return "Couldn't save that. Check your connection and try again.";
}

/** Why removing a family voice failed. */
function removeError(e: unknown): string {
  if (e instanceof ApiError && e.status === 403)
    return 'Only the person who made this voice, or the account that set up the pillow, can remove it.';
  return "Couldn't remove that voice. Check your connection and try again.";
}

/**
 * The voice the pillow speaks to her in: which one she hears now, every voice with Play to hear it
 * first (in the pillow's own warm line, or your own words), and family voices copied from a short
 * recording. Anyone in the care circle can listen, choose and add a voice.
 */
export function VoicePicker({ name }: { name: string }) {
  const { resident } = usePillow();
  const { pillowId } = usePillowLink();
  const residentId = resident?.id ?? null;
  const savedVoiceId = resident?.voice_id;
  const player = useVoicePlayer();
  const [choice, setChoice] = useState<VoiceChoice | null>(null);
  const [failed, setFailed] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [ownWords, setOwnWords] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Voice | null>(null);
  const [cloning, setCloning] = useState(false);

  const load = useCallback(() => {
    if (!residentId) return;
    readVoices(residentId, savedVoiceId).then(
      (next) => {
        setChoice(next);
        setFailed(false);
      },
      () => setFailed(true),
    );
  }, [residentId, savedVoiceId]);

  useEffect(() => {
    load();
  }, [load]);

  const choose = useCallback(
    async (voiceId: string) => {
      if (!residentId || !choice || choice.current === voiceId) return;
      const before = choice.current;
      setChoice((c) => (c ? { ...c, current: voiceId } : c));
      setStatus(null);
      try {
        const current = await chooseVoice(residentId, voiceId, choice.legacy ? (pillowId ?? undefined) : undefined);
        setChoice((c) => (c ? { ...c, current } : c));
        setStatus({ kind: 'saved', text: 'Saved' });
      } catch (e) {
        setChoice((c) => (c ? { ...c, current: before } : c));
        setStatus({ kind: 'error', text: chooseError(e, name) });
      }
    },
    [residentId, choice, pillowId, name],
  );

  const play = useCallback(
    (voice: Voice) => {
      if (!residentId) return;
      setStatus(null);
      player
        .toggle(voice.id, () => previewVoice(residentId, voice.id, ownWords ?? undefined))
        .catch((e) => setStatus({ kind: 'error', text: previewError(e) }));
    },
    [residentId, player, ownWords],
  );

  const remove = async (voice: Voice) => {
    setRemoving(null);
    if (!residentId) return;
    if (player.playing?.key === voice.id) player.stop();
    try {
      await deleteClone(residentId, voice.id);
      setStatus({ kind: 'saved', text: `Removed ${voice.name}.` });
      load();
    } catch (e) {
      setStatus({ kind: 'error', text: removeError(e) });
    }
  };

  if (failed) {
    return (
      <View className="items-start gap-2">
        <Text className="font-sans text-base text-ink-muted">
          Couldn&apos;t load the voices. Check your connection and try again.
        </Text>
        <Button
          variant="ghost"
          title="Try again"
          onPress={() => {
            setFailed(false);
            load();
          }}
        />
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

  const current = choice.voices.find((v) => v.id === choice.current);
  const stock = choice.voices.filter((v) => v.source === 'stock');
  const family = choice.voices.filter((v) => v.source === 'clone');
  const canPreview = !choice.legacy;
  const row = (voice: Voice) => (
    <VoiceOption
      key={voice.id}
      voice={voice}
      name={name}
      selected={voice.id === choice.current}
      playing={canPreview ? phaseOf(player.playing, voice.id) : undefined}
      onChoose={choose}
      onPlay={play}
      onRemove={voice.source === 'clone' ? setRemoving : undefined}
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

      {choice.voices.length === 0 ? (
        <Text className="font-sans text-base text-ink-muted">Voice choices arrive with the next pillow update.</Text>
      ) : (
        <View className="gap-2.5">{stock.map(row)}</View>
      )}

      {family.length ? (
        <View className="gap-2.5 pt-2">
          <Text accessibilityRole="header" className="font-sans-semibold text-sm text-ink-muted">
            Family voices
          </Text>
          {family.map(row)}
        </View>
      ) : null}

      <StatusLine status={status} />

      {canPreview ? (
        ownWords === null ? (
          <View className="-ml-6 -mt-2 items-start">
            <Button variant="ghost" title="Try your own words" onPress={() => setOwnWords('')} />
          </View>
        ) : (
          <View className="gap-1.5">
            <TextField
              label="Your own words"
              value={ownWords}
              onChangeText={setOwnWords}
              placeholder={`Goodnight ${name}, sleep well.`}
              maxLength={PREVIEW_MAX}
              returnKeyType="done"
              accessibilityHint="Press Play on a voice to hear it say this"
            />
            <View className="flex-row items-center justify-between gap-3">
              <Text className="flex-1 font-sans text-[13px] text-ink-muted">
                Press Play on any voice to hear it say this. {ownWords.length} of {PREVIEW_MAX}.
              </Text>
              <Button variant="ghost" title="Use the usual line" onPress={() => setOwnWords(null)} />
            </View>
          </View>
        )
      ) : (
        <Text className="-mt-2 font-sans text-sm text-ink-muted">
          Hearing a voice first, and adding a family voice, come with the next pillow update.
        </Text>
      )}

      {canPreview && residentId ? (
        <View className="gap-3 rounded-2xl border border-hairline p-4">
          <View className="gap-1">
            <Text className="font-sans-semibold text-base text-ink">A voice {name} knows</Text>
            <Text className="font-sans text-sm text-ink-muted">
              Record someone in the family reading for half a minute, and the pillow can speak to {name} in their voice.
            </Text>
          </View>
          <Button
            variant="secondary"
            title="Add a family voice"
            icon={<MicIconInk />}
            onPress={() => {
              player.stop();
              setCloning(true);
            }}
          />
        </View>
      ) : null}

      {residentId ? (
        <CloneVoiceSheet
          visible={cloning}
          name={name}
          residentId={residentId}
          player={player}
          onClose={() => setCloning(false)}
          onAdded={(voice) => setChoice((c) => (c ? { ...c, voices: [...c.voices, voice] } : c))}
          onUse={choose}
        />
      ) : null}

      <Dialog
        visible={removing !== null}
        title={`Remove ${removing?.name ?? 'this voice'}?`}
        body={
          removing?.id === choice.current
            ? `${name} hears this voice now. The pillow goes back to one of its own voices, and can't speak in this one again.`
            : "The pillow won't be able to speak in this voice any more."
        }
        confirmLabel="Remove voice"
        cancelLabel="Keep it"
        danger
        onConfirm={() => removing && remove(removing)}
        onCancel={() => setRemoving(null)}
      />
    </View>
  );
}

/** The mic in the secondary button's ink colour. */
function MicIconInk() {
  const { colors } = useTheme();
  return <MicIcon color={colors.ink} size={20} />;
}

type VoiceOptionProps = {
  voice: Voice;
  name: string;
  selected: boolean;
  /** Its preview's phase; undefined when previews aren't available. */
  playing: 'loading' | 'playing' | null | undefined;
  onChoose: (id: string) => void;
  onPlay: (voice: Voice) => void;
  onRemove?: (voice: Voice) => void;
};

/**
 * One voice: a round check and "In use" on the one she hears, Play on the right. Tapping the
 * name chooses it. "In use" sits on the name's line, so choosing never changes a row's size.
 */
function VoiceOption({ voice, name, selected, playing, onChoose, onPlay, onRemove }: VoiceOptionProps) {
  const { colors } = useTheme();
  const meta = voice.source === 'clone' ? madeBy(voice) : voice.description;
  return (
    <View
      className={`rounded-2xl bg-surface ${selected ? 'border-[1.5px] border-accent' : 'border-[1.5px] border-transparent'}`}
    >
      <View className="flex-row items-center gap-2 py-1.5 pl-1.5 pr-2.5">
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
          <View className="flex-1 gap-0.5">
            <View className="flex-row flex-wrap items-baseline gap-x-2">
              <Text className="font-sans-semibold text-base text-ink">{voice.name}</Text>
              {selected ? <Text className="font-sans-semibold text-[13px] text-accent-text">In use</Text> : null}
            </View>
            {meta ? <Text className="font-sans text-[13px] text-ink-muted">{meta}</Text> : null}
          </View>
        </Pressable>
        {playing !== undefined ? <PlayButton what={voice.name} state={playing} onPress={() => onPlay(voice)} /> : null}
      </View>
      {onRemove ? (
        <View className="-mt-2 flex-row justify-end px-1">
          <Button variant="ghost" title="Remove" onPress={() => onRemove(voice)} />
        </View>
      ) : null}
    </View>
  );
}
