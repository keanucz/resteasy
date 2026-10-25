import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Dialog, type Status, StatusLine } from '@/components/Feedback';
import { phaseOf, PlayButton, previewError } from '@/components/PlayButton';
import { ListRowSkeleton, SkeletonGroup } from '@/components/Skeleton';
import { Disclosure } from '@/components/voice/Disclosure';
import { RadioList } from '@/components/voice/RadioList';
import type { VoicePlayer } from '@/hooks/useVoicePlayer';
import { type Accent, copyWithAccent, readAccents, sampleUri, type Voice } from '@/services/voice';

type AccentSectionProps = {
  residentId: string;
  name: string;
  /** The voice she hears now, the one a copy is made of. */
  voice: Voice;
  player: VoicePlayer;
  onMade: (voice: Voice) => void;
  onUse: (voiceId: string) => void;
};

/**
 * Give the voice she hears another accent: a new copy that speaks with it, while the original
 * stays. Shown to the owner only, since a copy costs voice credits and only the owner can use it.
 */
export function AccentSection({ residentId, name, voice, player, onMade, onUse }: AccentSectionProps) {
  const [accents, setAccents] = useState<Accent[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<Voice | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    readAccents(residentId).then(setAccents, () =>
      setStatus({ kind: 'error', text: "Couldn't load the accents. Check your connection and try again." }),
    );
  }, [residentId]);

  const accent = accents?.find((a) => a.id === picked) ?? null;
  // A copy keeps the voice it came from, so another accent starts from that voice's name too.
  const baseName = voice.source === 'accent' ? voice.name.split(',')[0] : voice.name;

  const play = (v: Voice) =>
    player.toggle(v.id, () => sampleUri(residentId, v)).catch((e) => setStatus({ kind: 'error', text: previewError(e) }));

  const make = async () => {
    setAsking(false);
    if (!accent) return;
    player.stop();
    setBusy(true);
    setStatus(null);
    setMade(null);
    try {
      const copy = await copyWithAccent(residentId, voice.id, accent.id);
      onMade(copy);
      setMade(copy);
      play(copy);
    } catch {
      setStatus({ kind: 'error', text: `Couldn't make a ${accent.name} copy. Try again in a moment.` });
    } finally {
      setBusy(false);
    }
  };

  if (!accents) {
    return status ? (
      <StatusLine status={status} />
    ) : (
      <SkeletonGroup>
        <View className="gap-2.5">
          <ListRowSkeleton />
          <ListRowSkeleton />
        </View>
      </SkeletonGroup>
    );
  }

  return (
    <View className="gap-4">
      <Disclosure title="Accent" value={accent?.name ?? 'Choose one'}>
        <RadioList
          label="Accent"
          options={accents.map((a) => ({ value: a.id, label: a.name }))}
          value={picked}
          onChange={(id) => {
            setPicked(id);
            setMade(null);
          }}
        />
      </Disclosure>
      <Button
        fullWidth
        variant="secondary"
        title={accent ? `Make ${baseName} sound ${accent.name}` : 'Choose an accent first'}
        loading={busy}
        disabled={!accent}
        onPress={() => setAsking(true)}
      />
      {busy ? (
        <Text accessibilityLiveRegion="polite" className="font-sans text-[13px] text-ink-muted">
          Making the new voice. This takes a few seconds.
        </Text>
      ) : null}

      {made ? (
        <View className="gap-3 rounded-2xl border border-hairline p-4">
          <Text className="font-sans-semibold text-base text-ink">{made.name} is ready</Text>
          <PlayButton fullWidth title="Hear it" what={made.name} state={phaseOf(player.playing, made.id)} onPress={() => play(made)} />
          <Button fullWidth title={`Use for ${name}'s pillow`} onPress={() => onUse(made.id)} />
        </View>
      ) : null}
      <StatusLine status={status} />

      <Dialog
        visible={asking}
        title={`Make ${baseName} sound ${accent?.name ?? ''}?`}
        body={`This makes a new voice: ${baseName} with this accent. ${baseName} stays as it is.`}
        confirmLabel="Make the copy"
        cancelLabel="Not now"
        onConfirm={make}
        onCancel={() => setAsking(false)}
      />
    </View>
  );
}
