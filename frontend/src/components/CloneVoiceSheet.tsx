import * as DocumentPicker from 'expo-document-picker';
import {
  IOSOutputFormat,
  RecordingPresets,
  type RecordingOptions,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useRef, useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Sheet } from '@/components/Feedback';
import { phaseOf, PlayButton, previewError } from '@/components/PlayButton';
import { Checkbox } from '@/components/Selection';
import { MicIcon, StopIcon } from '@/components/TabIcons';
import { TextField } from '@/components/TextField';
import { Disclosure } from '@/components/voice/Disclosure';
import { RadioList } from '@/components/voice/RadioList';
import type { VoicePlayer } from '@/hooks/useVoicePlayer';
import { useTheme } from '@/hooks/useTheme';
import { ApiError } from '@/services/api';
import {
  type Accent,
  CLIP_MAX_S,
  CLIP_MIN_S,
  type Clip,
  clipFromRecording,
  cloneVoice,
  sampleUri,
  type Voice,
  VOICE_NAME_MAX,
} from '@/services/voice';

/**
 * Cartesia clones from flac, mp3, ogg, wav or webm, so iPhones record plain wav (an .m4a may be
 * refused). Android has no such encoder and keeps the AAC preset; the web records webm.
 */
const CLONE_RECORDING: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  extension: '.wav',
  ios: {
    ...RecordingPresets.HIGH_QUALITY.ios,
    extension: '.wav',
    outputFormat: IOSOutputFormat.LINEARPCM,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  android: RecordingPresets.HIGH_QUALITY.android,
};

/** How often the timer reads the recorder while recording. */
const TICK_MS = 250;

/** A warm passage to read aloud: about 20 seconds at a gentle pace, in the words the pillow will use with her. */
const script = (name: string) =>
  `Hello ${name}, it's me. I hope today was a gentle one. It's nearly time to rest, so get cosy and let the ` +
  `pillow look after you tonight. If you need anything at all, I'm only a call away. Sleep tight, and I'll ` +
  `talk to you in the morning.`;

/** 0:07 */
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

/** Why copying the voice failed, in words the family member can act on. */
function uploadError(e: unknown, name: string): string {
  if (e instanceof ApiError && e.status === 404) return 'Adding a family voice comes with the next pillow update.';
  if (e instanceof ApiError && e.status === 403) return `Only people in ${name}'s care circle can add a voice.`;
  if (e instanceof ApiError && e.status === 413)
    return `That recording is too large. Keep it under ${CLIP_MAX_S} seconds.`;
  if (e instanceof ApiError && (e.status === 400 || e.status === 415 || e.status === 422))
    return `The pillow couldn't use that recording. Try ${CLIP_MIN_S} to ${CLIP_MAX_S} seconds of clear speech in a quiet room.`;
  return "Couldn't send the recording. Check your connection and try again.";
}

type Recorded = { clip: Clip; from: 'mic' | 'file'; seconds: number | null; fileName?: string };

type CloneVoiceSheetProps = {
  visible: boolean;
  /** Her preferred name. */
  name: string;
  residentId: string;
  /** The screen's player, so a voice in the list and a recording here never play over each other. */
  player: VoicePlayer;
  /** Accents the speaker may have, so the copy keeps theirs; none hides the choice. */
  accents?: Accent[];
  /** Only the owner can make the new voice the one she hears. */
  canUse?: boolean;
  onClose: () => void;
  onAdded: (voice: Voice) => void;
  onUse: (voiceId: string) => void;
};

/**
 * Copy a family voice: read a short passage into the mic (or pick a recording), name it, say the
 * speaker agreed, and send it. Then hear the new voice and use it for her pillow.
 */
export function CloneVoiceSheet({
  visible,
  name,
  residentId,
  player,
  accents = [],
  canUse = true,
  onClose,
  onAdded,
  onUse,
}: CloneVoiceSheetProps) {
  const { colors } = useTheme();
  const [recorded, setRecorded] = useState<Recorded | null>(null);
  const [voiceName, setVoiceName] = useState('');
  // '' is "not sure": the copy then keeps whatever accent it hears
  const [accent, setAccent] = useState('');
  const [consent, setConsent] = useState(false);
  const [micDenied, setMicDenied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<Voice | null>(null);
  const startedAt = useRef(0);
  const recording = useRef(false);

  /** Keeps what the mic caught. Called once per recording, from the stop button or when it hits 30 s. */
  const finish = useCallback((uri: string | null) => {
    if (!recording.current) return;
    recording.current = false;
    setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => {});
    if (uri)
      setRecorded({ clip: clipFromRecording(uri), from: 'mic', seconds: (Date.now() - startedAt.current) / 1000 });
  }, []);

  const recorder = useAudioRecorder(CLONE_RECORDING, (status) => {
    if (status.isFinished) finish(status.url);
  });
  const recorderState = useAudioRecorderState(recorder, TICK_MS);
  const isRecording = recorderState.isRecording;
  const elapsed = isRecording ? recorderState.durationMillis / 1000 : 0;

  const startRecording = async () => {
    setError(null);
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setMicDenied(true);
      return;
    }
    setMicDenied(false);
    player.stop();
    try {
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      setRecorded(null);
      startedAt.current = Date.now();
      recording.current = true;
      recorder.record({ forDuration: CLIP_MAX_S });
    } catch {
      recording.current = false;
      setError("Couldn't start the microphone. Try again, or choose an audio file instead.");
    }
  };

  const stopRecording = async () => {
    await recorder.stop().catch(() => {});
    finish(recorder.uri);
  };

  const pickFile = async () => {
    setError(null);
    player.stop();
    const picked = await DocumentPicker.getDocumentAsync({ type: 'audio/*', copyToCacheDirectory: true });
    const asset = picked.canceled ? null : picked.assets[0];
    if (!asset) return;
    setRecorded({
      clip: { uri: asset.uri, name: asset.name, mimeType: asset.mimeType ?? 'audio/mpeg' },
      from: 'file',
      seconds: null,
      fileName: asset.name,
    });
  };

  const close = () => {
    if (recording.current) recorder.stop().catch(() => {});
    recording.current = false;
    player.stop();
    onClose();
    // Start fresh next time.
    setRecorded(null);
    setVoiceName('');
    setAccent('');
    setConsent(false);
    setMicDenied(false);
    setError(null);
    setMade(null);
  };

  const tooShort = recorded?.seconds !== null && recorded?.seconds !== undefined && recorded.seconds < CLIP_MIN_S;
  const missing = [
    !recorded ? 'a recording' : tooShort ? 'a longer recording' : null,
    voiceName.trim() ? null : 'a name',
    consent ? null : 'their agreement',
  ].filter(Boolean) as string[];

  const send = async () => {
    if (!recorded || missing.length) return;
    player.stop();
    setBusy(true);
    setError(null);
    try {
      const voice = await cloneVoice(residentId, recorded.clip, voiceName, accent || undefined);
      onAdded(voice);
      setMade(voice);
    } catch (e) {
      setError(uploadError(e, name));
    } finally {
      setBusy(false);
    }
  };

  const listen = (key: string, load: () => Promise<string>) =>
    player.toggle(key, load).catch((e) => setError(previewError(e)));

  const footer = made ? (
    <>
      {canUse ? (
        <Button
          fullWidth
          title={`Use for ${name}'s pillow`}
          onPress={() => {
            onUse(made.id);
            close();
          }}
        />
      ) : null}
      <Button fullWidth variant={canUse ? 'ghost' : 'primary'} title="Done" onPress={close} />
    </>
  ) : (
    <>
      {missing.length && !busy ? (
        <Text className="font-sans text-[13px] text-ink-muted">Still needed: {listWords(missing)}.</Text>
      ) : null}
      {busy ? (
        <Text accessibilityLiveRegion="polite" className="font-sans text-[13px] text-ink-muted">
          Sending the recording. This takes a few seconds.
        </Text>
      ) : null}
      <Button fullWidth title="Copy this voice" loading={busy} disabled={missing.length > 0} onPress={send} />
    </>
  );

  return (
    <Sheet
      visible={visible}
      title={made ? `${made.name} is ready` : 'Add a family voice'}
      note={
        made
          ? `This is how the pillow will sound to ${name}.`
          : `Record someone ${name} knows reading the passage below. The pillow learns to speak to ${name} in their voice.`
      }
      onClose={close}
      footer={footer}
    >
      {made ? (
        <View className="gap-4">
          <PlayButton
            fullWidth
            title="Hear it"
            what={`${made.name}'s voice`}
            state={phaseOf(player.playing, made.id)}
            onPress={() => listen(made.id, () => sampleUri(residentId, made))}
          />
          <Text className="font-sans text-sm text-ink-muted">
            If it doesn&apos;t sound like them, remove it from the list and record again somewhere quiet.
          </Text>
          {error ? <ErrorText text={error} /> : null}
        </View>
      ) : (
        <>
          <View className="gap-2 rounded-2xl bg-surface p-4">
            <Text className="font-sans-semibold text-[13px] text-ink-muted">Read this aloud, slowly and warmly</Text>
            <Text className="font-display-italic text-[17px] leading-7 text-ink">{script(name)}</Text>
          </View>

          {isRecording ? (
            <View className="gap-3" accessibilityLiveRegion="polite">
              <View className="flex-row items-baseline gap-2">
                <Text className="font-display text-3xl text-ink" style={{ fontVariant: ['tabular-nums'] }}>
                  {clock(elapsed)}
                </Text>
                <Text className="font-sans text-sm text-ink-muted">of {clock(CLIP_MAX_S)}, recording</Text>
              </View>
              <TimerBar seconds={elapsed} />
              <Text className="font-sans text-sm text-ink-muted">
                {elapsed < CLIP_MIN_S
                  ? `Keep going: at least ${CLIP_MIN_S} seconds.`
                  : 'That is enough. Stop whenever you are ready.'}
              </Text>
              <Button
                fullWidth
                title="Stop recording"
                icon={<StopIcon color={colors['on-accent']} size={16} />}
                onPress={stopRecording}
              />
            </View>
          ) : recorded ? (
            <View className="gap-3 rounded-2xl border border-hairline p-4">
              <Text className="font-sans-semibold text-base text-ink">
                {recorded.from === 'file'
                  ? `Using ${recorded.fileName}`
                  : `Recording ready, ${Math.round(recorded.seconds ?? 0)} seconds`}
              </Text>
              {tooShort ? (
                <ErrorText
                  text={`That was ${Math.round(recorded.seconds ?? 0)} seconds. Record at least ${CLIP_MIN_S} so the copy sounds like them.`}
                />
              ) : null}
              <View className="flex-row flex-wrap items-center gap-2">
                <PlayButton
                  title="Listen"
                  what={recorded.from === 'file' ? 'the file' : 'your recording'}
                  state={phaseOf(player.playing, 'clip')}
                  onPress={() => listen('clip', async () => recorded.clip.uri)}
                />
                <Button
                  variant="ghost"
                  title={recorded.from === 'file' ? 'Choose another' : 'Record again'}
                  onPress={recorded.from === 'file' ? pickFile : startRecording}
                />
              </View>
            </View>
          ) : (
            <View className="gap-1">
              <Button
                fullWidth
                title="Start recording"
                icon={<MicIcon color={colors['on-accent']} size={20} />}
                onPress={startRecording}
              />
              <Text className="pt-1 text-center font-sans text-[13px] text-ink-muted">
                {CLIP_MIN_S} to {CLIP_MAX_S} seconds. It stops by itself at {CLIP_MAX_S}.
              </Text>
            </View>
          )}

          {micDenied ? (
            <ErrorText text="Rest Easy isn't allowed to use the microphone. Turn it on in your phone's Settings, or choose an audio file instead." />
          ) : null}

          {!isRecording && recorded?.from !== 'file' ? (
            <View className="-mt-3 items-center">
              <Button variant="ghost" title="Choose an audio file instead" onPress={pickFile} />
            </View>
          ) : null}

          <View className="gap-1">
            <TextField
              label="Whose voice is it?"
              value={voiceName}
              onChangeText={setVoiceName}
              placeholder="For example, Sam"
              maxLength={VOICE_NAME_MAX}
              autoCapitalize="words"
              returnKeyType="done"
            />
            <Text className="font-sans text-[13px] text-ink-muted">Shown in the list of voices.</Text>
          </View>

          {accents.length ? (
            <Disclosure title="Their accent" value={accents.find((a) => a.id === accent)?.name ?? 'Not sure'}>
              <Text className="font-sans text-[13px] text-ink-muted">Helps the copy keep the way they speak.</Text>
              <RadioList
                label="Their accent"
                options={[{ value: '', label: 'Not sure' }, ...accents.map((a) => ({ value: a.id, label: a.name }))]}
                value={accent}
                onChange={setAccent}
              />
            </Disclosure>
          ) : null}

          <Checkbox
            label="The person recording agreed to have their voice copied for this pillow"
            checked={consent}
            onChange={setConsent}
          />

          {error ? <ErrorText text={error} /> : null}
        </>
      )}
    </Sheet>
  );
}

/** "a, b and c" */
function listWords(words: string[]): string {
  return words.length < 2 ? words.join('') : `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

function ErrorText({ text }: { text: string }) {
  return (
    <Text accessibilityLiveRegion="polite" className="font-sans text-sm text-danger-text">
      {text}
    </Text>
  );
}

/** How far into the 30 seconds the recording is, with a mark where it becomes long enough. */
function TimerBar({ seconds }: { seconds: number }) {
  const done = Math.min(1, seconds / CLIP_MAX_S);
  return (
    <View className="h-2 overflow-hidden rounded-full bg-field" accessible={false}>
      <View className="h-full rounded-full bg-accent" style={{ width: `${done * 100}%` }} />
      <View
        className="absolute bottom-0 top-0 w-0.5 bg-ink/40"
        style={{ left: `${(CLIP_MIN_S / CLIP_MAX_S) * 100}%` }}
      />
    </View>
  );
}
