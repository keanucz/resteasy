import { memo, useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Dialog, type Status, StatusLine } from '@/components/Feedback';
import { phaseOf, PlayButton, previewError } from '@/components/PlayButton';
import { ListRowSkeleton, SkeletonGroup } from '@/components/Skeleton';
import { TextField } from '@/components/TextField';
import { Disclosure } from '@/components/voice/Disclosure';
import { loadOnce, type Playing, type VoicePlayer } from '@/hooks/useVoicePlayer';
import { ApiError } from '@/services/api';
import {
  addPronunciation,
  forgetPreviews,
  previewVoice,
  type Pronunciation,
  readPronunciations,
  removePronunciation,
  SOUNDS_LIKE_MAX,
  WORD_MAX,
} from '@/services/voice';

/** A short line to hear a word in. */
const tryLine = (word: string) => `Goodnight, ${word}. Sleep well.`;

/** Why adding or removing a word failed. */
function wordError(e: unknown): string {
  if (e instanceof ApiError && e.status === 409) return 'That word is already in the list. Remove it first to change it.';
  if (e instanceof ApiError && e.status === 403)
    return 'Only the person who added this word, or the account that set up the pillow, can remove it.';
  // The backend words a full list itself; any other 422 is a field it couldn't read.
  if (e instanceof ApiError && e.status === 422)
    return e.message.startsWith('Request failed') ? 'Check the word and how to say it.' : e.message;
  return "Couldn't save that. Check your connection and try again.";
}

type WordsSectionProps = {
  residentId: string;
  /** The voice she hears, which every word is tried in. */
  voiceId: string;
  player: VoicePlayer;
};

/**
 * Names, places and medicines the pillow should say right. Spell a word the way it sounds, hear
 * it, and add it: from then on the pillow says it that way, in every voice.
 */
export function WordsSection({ residentId, voiceId, player }: WordsSectionProps) {
  const [words, setWords] = useState<Pronunciation[] | null>(null);
  const [removing, setRemoving] = useState<Pronunciation | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  const { playing, toggle } = player;

  useEffect(() => {
    let cancelled = false;
    readPronunciations(residentId).then(
      (found) => {
        if (!cancelled) setWords(found);
      },
      () => {
        if (!cancelled)
          setStatus({ kind: 'error', text: "Couldn't load the words. Check your connection and try again." });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [residentId]);

  const hear = useCallback(
    (key: string, text: string) => {
      setStatus(null);
      toggle(key, () =>
        loadOnce(`preview|${residentId}|${voiceId}|${text}`, () => previewVoice(residentId, voiceId, text)),
      ).catch((e) => setStatus({ kind: 'error', text: previewError(e) }));
    },
    [residentId, voiceId, toggle],
  );

  /** Teaches the pillow the word; true when it took, so the form can clear. */
  const add = useCallback(
    async (word: string, soundsLike: string): Promise<boolean> => {
      setStatus(null);
      try {
        const added = await addPronunciation(residentId, word, soundsLike);
        setWords((w) => [...(w ?? []), added]);
        forgetPreviews();
        setStatus({ kind: 'saved', text: `Added. The pillow says ${added.word} like "${added.sounds_like}" now.` });
        return true;
      } catch (e) {
        setStatus({ kind: 'error', text: wordError(e) });
        return false;
      }
    },
    [residentId],
  );

  const remove = async (w: Pronunciation) => {
    setRemoving(null);
    setStatus(null);
    try {
      await removePronunciation(residentId, w.id);
      setWords((all) => (all ?? []).filter((x) => x.id !== w.id));
      forgetPreviews();
      setStatus({ kind: 'saved', text: `Removed ${w.word}.` });
    } catch (e) {
      setStatus({ kind: 'error', text: wordError(e) });
    }
  };

  return (
    <View className="gap-4">
      {words === null ? (
        status ? null : (
          <SkeletonGroup>
            <ListRowSkeleton />
          </SkeletonGroup>
        )
      ) : words.length === 0 ? (
        <Text className="font-sans text-base text-ink-muted">No words yet. Start with her own name.</Text>
      ) : (
        <View className="gap-2.5">
          {words.map((w) => (
            <WordRow key={w.id} word={w} state={phaseOf(playing, w.id)} onHear={hear} onRemove={setRemoving} />
          ))}
        </View>
      )}

      <Disclosure title="Add a word">
        <AddWord playing={playing} onHear={hear} onAdd={add} />
      </Disclosure>
      <StatusLine status={status} />

      <Dialog
        visible={removing !== null}
        title={`Remove ${removing?.word ?? 'this word'}?`}
        body="The pillow goes back to saying it its own way."
        confirmLabel="Remove word"
        cancelLabel="Keep it"
        danger
        onConfirm={() => removing && remove(removing)}
        onCancel={() => setRemoving(null)}
      />
    </View>
  );
}

type WordRowProps = {
  word: Pronunciation;
  state: 'loading' | 'playing' | null;
  onHear: (key: string, text: string) => void;
  onRemove: (word: Pronunciation) => void;
};

/** One word the pillow says her way, with Play to hear it and Remove. */
const WordRow = memo(function WordRow({ word: w, state, onHear, onRemove }: WordRowProps) {
  return (
    <View className="rounded-2xl bg-surface">
      <View className="flex-row items-center gap-3 py-3 pl-3.5 pr-2.5">
        <View className="flex-1 gap-0.5">
          <Text className="font-sans-semibold text-base text-ink">{w.word}</Text>
          <Text className="font-sans text-[13px] text-ink-muted">
            Said like &quot;{w.sounds_like}&quot;{w.created_by_name ? `. Added by ${w.created_by_name}.` : '.'}
          </Text>
        </View>
        <PlayButton what={w.word} state={state} onPress={() => onHear(w.id, tryLine(w.word))} />
      </View>
      <View className="flex-row justify-end px-1 pb-1">
        <Button variant="ghost" title="Remove" onPress={() => onRemove(w)} />
      </View>
    </View>
  );
});

type AddWordProps = {
  playing: Playing;
  onHear: (key: string, text: string) => void;
  onAdd: (word: string, soundsLike: string) => Promise<boolean>;
};

/**
 * The form for a new word. It keeps what is typed to itself, so typing doesn't redraw the list
 * above, and what was typed stays when adding fails.
 */
function AddWord({ playing, onHear, onAdd }: AddWordProps) {
  const [word, setWord] = useState('');
  const [soundsLike, setSoundsLike] = useState('');
  const ready = word.trim().length > 0 && soundsLike.trim().length > 0;

  const add = async () => {
    if (!(await onAdd(word, soundsLike))) return;
    setWord('');
    setSoundsLike('');
  };

  return (
    <View className="gap-3 rounded-2xl border border-hairline p-4">
      <TextField
        label="Word"
        value={word}
        onChangeText={setWord}
        placeholder="For example, Siobhan"
        maxLength={WORD_MAX}
        autoCapitalize="words"
      />
      <View className="gap-1">
        <TextField
          label="Say it like"
          value={soundsLike}
          onChangeText={setSoundsLike}
          placeholder="shiv-AWN"
          maxLength={SOUNDS_LIKE_MAX}
          autoCapitalize="none"
        />
        <Text className="font-sans text-[13px] text-ink-muted">
          Spell it the way it sounds, with the loud part in capitals.
        </Text>
      </View>
      <View className="flex-row flex-wrap items-center gap-2">
        <PlayButton
          title="Hear it"
          what="how it will sound"
          state={phaseOf(playing, 'new-word')}
          onPress={() => ready && onHear('new-word', tryLine(soundsLike.trim()))}
        />
        <View className="flex-1">
          <Button fullWidth title="Add word" disabled={!ready} onPress={add} />
        </View>
      </View>
    </View>
  );
}
