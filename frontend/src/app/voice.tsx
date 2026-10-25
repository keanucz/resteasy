import { Redirect, router } from 'expo-router';
import { type ReactNode, useCallback, useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { Button, IconButton } from '@/components/Button';
import { CloneVoiceSheet } from '@/components/CloneVoiceSheet';
import { Dialog, type Status, StatusLine } from '@/components/Feedback';
import { phaseOf, previewError } from '@/components/PlayButton';
import { ListRowSkeleton, SkeletonGroup } from '@/components/Skeleton';
import { MicIcon } from '@/components/TabIcons';
import { AccentSection } from '@/components/voice/AccentSection';
import { StyleSection } from '@/components/voice/StyleSection';
import { VoiceRow } from '@/components/voice/VoiceRow';
import { WordsSection } from '@/components/voice/WordsSection';
import { usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';
import { useVoicePlayer } from '@/hooks/useVoicePlayer';
import { useVoices } from '@/hooks/useVoices';
import { ApiError } from '@/services/api';
import { type Accent, deleteClone, readAccents, sampleUri, type Voice } from '@/services/voice';

/** Why removing a family voice failed. */
function removeError(e: unknown): string {
  if (e instanceof ApiError && e.status === 403)
    return 'Only the person who made this voice, or the account that set up the pillow, can remove it.';
  return "Couldn't remove that voice. Check your connection and try again.";
}

/**
 * Custom voice: everything about how the pillow sounds to her beyond picking a voice. Family
 * voices copied from a recording, another accent for the voice she hears, how it speaks (speed,
 * volume, tone), and words it should say her way. Reached from Settings' voice section.
 */
export default function CustomVoiceScreen() {
  const { session, loading } = useSession();
  const { pillowId } = usePillowLink();
  const { resident } = usePillow();
  const insets = useSafeAreaInsets();
  const name = resident?.preferred_name ?? 'her';
  const voices = useVoices(name);
  const { residentId, choice, failed, isOwner, reload, choose, add, setChoice } = voices;
  const player = useVoicePlayer();
  const [accents, setAccents] = useState<Accent[]>([]);
  const [cloning, setCloning] = useState(false);
  const [removing, setRemoving] = useState<Voice | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    if (residentId) readAccents(residentId).then(setAccents, () => setAccents([]));
  }, [residentId]);

  // Stop whatever is playing when leaving the page.
  useEffect(() => () => player.stop(), [player]);

  const play = useCallback(
    (voice: Voice) => {
      if (!residentId) return;
      setStatus(null);
      player
        .toggle(voice.id, () => sampleUri(residentId, voice))
        .catch((e) => setStatus({ kind: 'error', text: previewError(e) }));
    },
    [residentId, player],
  );

  const use = useCallback(
    async (voiceId: string) => {
      setStatus(null);
      setStatus(await choose(voiceId));
    },
    [choose],
  );

  const remove = async (voice: Voice) => {
    setRemoving(null);
    if (!residentId) return;
    if (player.playing?.key === voice.id) player.stop();
    try {
      await deleteClone(residentId, voice.id);
      setStatus({ kind: 'saved', text: `Removed ${voice.name}.` });
      reload();
    } catch (e) {
      setStatus({ kind: 'error', text: removeError(e) });
    }
  };

  // useSession reads the stored session again on every mount, so it starts empty: only a session
  // known to be missing goes to the login (redirecting sooner bounced the page straight back).
  if (!loading && !session) return <Redirect href="/login" />;
  if (!pillowId) return <Redirect href="/" />;

  const current = choice?.voices.find((v) => v.id === choice.current);
  const own = choice?.voices.filter((v) => v.source !== 'stock') ?? [];

  return (
    <ScrollView
      className="flex-1 bg-canvas"
      contentContainerClassName="gap-8 px-4 pb-12"
      contentContainerStyle={{ paddingTop: insets.top + 12 }}
      keyboardShouldPersistTaps="handled"
    >
      <View className="gap-4">
        <BackButton />
        <View className="gap-1">
          <Text accessibilityRole="header" className="font-display text-3xl text-ink">
            Custom voice
          </Text>
          <Text className="font-sans text-sm text-ink-muted">How {name}&apos;s pillow sounds, and who it sounds like.</Text>
          {choice && !isOwner ? (
            <Text className="pt-2 font-sans text-sm text-ink">
              You can listen, add family voices and add words. Only the account that set up the pillow can change
              what {name} hears.
            </Text>
          ) : null}
        </View>
      </View>

      {failed ? (
        <View className="items-start gap-2">
          <Text className="font-sans text-base text-ink-muted">
            Couldn&apos;t load the voices. Check your connection and try again.
          </Text>
          <Button variant="ghost" title="Try again" onPress={reload} />
        </View>
      ) : !choice || !residentId ? (
        <SkeletonGroup>
          <View className="gap-2.5">
            <ListRowSkeleton />
            <ListRowSkeleton />
            <ListRowSkeleton />
          </View>
        </SkeletonGroup>
      ) : choice.legacy ? (
        <Text className="font-sans text-base text-ink-muted">
          Making your own voice comes with the next pillow update.
        </Text>
      ) : (
        <>
          <Section
            title="Family voices"
            note={`Record someone ${name} knows reading for half a minute, and the pillow can speak in their voice.`}
          >
            {own.length ? (
              <View className="gap-2.5">
                {own.map((voice) => (
                  <VoiceRow
                    key={voice.id}
                    voice={voice}
                    name={name}
                    selected={voice.id === choice.current}
                    canChoose={isOwner}
                    playing={phaseOf(player.playing, voice.id)}
                    onChoose={use}
                    onPlay={play}
                    onRemove={setRemoving}
                  />
                ))}
              </View>
            ) : null}
            <Button
              fullWidth
              variant="secondary"
              title="Add a family voice"
              icon={<MicIconInk />}
              onPress={() => {
                player.stop();
                setCloning(true);
              }}
            />
            <StatusLine status={status} />
          </Section>

          <Section title="How it speaks" note="Speed, volume and tone, for every voice. Try it before you save.">
            <StyleSection
              residentId={residentId}
              name={name}
              voiceId={choice.current}
              saved={choice.style}
              emotions={choice.emotions}
              isOwner={isOwner}
              player={player}
              onSaved={(style) => setChoice((c) => ({ ...c, style }))}
            />
          </Section>

          <Section
            title="Names and words"
            note={`Names, places and medicines the pillow should say right, in every voice.`}
          >
            <WordsSection residentId={residentId} voiceId={choice.current} player={player} />
          </Section>

          {/* Last and owner only: the rarest change, and each copy is a new paid voice. */}
          {current && isOwner ? (
            <Section
              title="Accent"
              note={`Give ${current.name} another accent. This makes a new voice, and ${current.name} stays as it is.`}
            >
              <AccentSection
                residentId={residentId}
                name={name}
                voice={current}
                player={player}
                onMade={add}
                onUse={use}
              />
            </Section>
          ) : null}

          <CloneVoiceSheet
            visible={cloning}
            name={name}
            residentId={residentId}
            player={player}
            accents={accents}
            canUse={isOwner}
            onClose={() => setCloning(false)}
            onAdded={add}
            onUse={use}
          />

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
        </>
      )}
    </ScrollView>
  );
}

/** A titled part of the page with a line saying what it is for. */
function Section({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <View className="gap-4">
      <View className="gap-1">
        <Text accessibilityRole="header" className="font-display text-xl text-ink">
          {title}
        </Text>
        <Text className="font-sans text-sm text-ink-muted">{note}</Text>
      </View>
      {children}
    </View>
  );
}

/** The mic in the secondary button's ink colour. */
function MicIconInk() {
  const { colors } = useTheme();
  return <MicIcon color={colors.ink} size={20} />;
}

function BackButton() {
  const { colors } = useTheme();
  return (
    <IconButton label="Back" onPress={() => (router.canGoBack() ? router.back() : router.replace('/settings'))}>
      <Svg width={20} height={20} viewBox="0 0 24 24">
        <Path
          d="M15 5 L8 12 L15 19"
          stroke={colors.ink}
          strokeWidth={2}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    </IconButton>
  );
}
