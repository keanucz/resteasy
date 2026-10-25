import * as DocumentPicker from 'expo-document-picker';
import {
  type AudioRecorder,
  RecordingPresets,
  type RecordingOptions,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';
import { File } from 'expo-file-system';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';

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
 * Phones record the preset's AAC .m4a and the web records webm; Cartesia clones from both. iPhones
 * used to record linear PCM wav, but AVAudioRecorder captured nothing with those settings while the
 * clock still ran, so the copy was never sent.
 */
const CLONE_RECORDING: RecordingOptions = {
  ...RecordingPresets.HIGH_QUALITY,
  // One voice needs one channel: a 60 s clip is ~0.5 MB, so it uploads fast and fits the 10 MB cap.
  numberOfChannels: 1,
  bitRate: 64000,
};

/** A recording smaller than this has no sound in it (an empty file is a few hundred bytes). */
const CLIP_MIN_BYTES = 4096;

/** The recording's size in bytes, or null when it can't be read (the web, or a missing file). */
function clipBytes(uri: string): number | null {
  if (Platform.OS === 'web') return null;
  try {
    return new File(uri).size;
  } catch {
    return null;
  }
}

/** How often the timer reads the recorder while recording. */
const TICK_MS = 250;

/**
 * How long to wait for a copy before giving up on it. Cartesia can take tens of seconds. The upload
 * carries on after this, so a copy that arrives late is still listed; leaving the screen cancels it.
 */
const UPLOAD_TIMEOUT_MS = 90_000;
/** When the waiting message admits it is taking a while. */
const UPLOAD_SLOW_MS = 15_000;

/** Back to playing through the speaker, after recording or a failed start. */
const restorePlayback = () => setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => {});

/** The upload ran past UPLOAD_TIMEOUT_MS. */
class UploadTimeout extends Error {}

/** Where the mic is: one recording at a time, and start and stop never overlap. */
type Phase = 'idle' | 'starting' | 'recording' | 'stopping';

/** A warm passage to read aloud: about 20 seconds at a gentle pace, in the words the pillow will use with her. */
const script = (name: string) =>
  `Hello ${name}, it's me. I hope today was a gentle one. It's nearly time to rest, so get cosy and let the ` +
  `pillow look after you tonight. If you need anything at all, I'm only a call away. Sleep tight, and I'll ` +
  `talk to you in the morning.`;

/** 0:07 */
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

/** Why copying the voice failed, in words the family member can act on. */
function uploadError(e: unknown, name: string): string {
  if (e instanceof UploadTimeout) return 'Copying the voice is taking too long. Check your connection and try again.';
  if (e instanceof ApiError && e.status === 404) return 'Adding a family voice comes with the next pillow update.';
  if (e instanceof ApiError && e.status === 403) return `Only people in ${name}'s care circle can add a voice.`;
  if (e instanceof ApiError && e.status === 413)
    return `That recording is too large. Keep it under ${CLIP_MAX_S} seconds.`;
  if (e instanceof ApiError && (e.status === 400 || e.status === 415 || e.status === 422))
    return `The pillow couldn't use that recording. Try ${CLIP_MIN_S} to ${CLIP_MAX_S} seconds of clear speech in a quiet room.`;
  return "Couldn't send the recording. Check your connection and try again.";
}

const NO_ACCENTS: Accent[] = [];

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
  accents = NO_ACCENTS,
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
  // True once an upload has run for UPLOAD_SLOW_MS, so the waiting message can say so
  const [slow, setSlow] = useState(false);
  const [phase, setPhaseState] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<Voice | null>(null);
  const startedAt = useRef(0);
  // Read by handlers that run between renders, so a second tap sees the first one at once
  const phaseRef = useRef<Phase>('idle');
  const picking = useRef(false);
  const uploading = useRef<object | null>(null);
  // Bumped on close and unmount, so a start, pick or upload that ends later leaves the sheet alone
  const session = useRef(0);
  const mounted = useRef(true);
  /** Cancels the upload under way when the sheet goes away, so it stops holding the connection. */
  const upload = useRef<AbortController | null>(null);

  const isLive = useCallback((at: number) => mounted.current && session.current === at, []);

  const setPhase = useCallback((next: Phase) => {
    phaseRef.current = next;
    if (mounted.current) setPhaseState(next);
  }, []);

  /** Keeps what the mic caught. Runs once per recording, from the stop button or when it hits CLIP_MAX_S. */
  const finish = useCallback(
    (uri: string | null) => {
      if (phaseRef.current !== 'recording' && phaseRef.current !== 'stopping') return;
      setPhase('idle');
      restorePlayback();
      const bytes = uri ? clipBytes(uri) : null;
      if (!uri || (bytes !== null && bytes < CLIP_MIN_BYTES)) {
        setError("The microphone didn't pick anything up. Try again, or choose an audio file instead.");
        return;
      }
      setRecorded({ clip: clipFromRecording(uri), from: 'mic', seconds: (Date.now() - startedAt.current) / 1000 });
    },
    [setPhase],
  );

  /** The recorder stopped by itself. While the stop button is finalising the file, it finishes instead. */
  const ended = useCallback(
    (uri: string | null) => {
      if (phaseRef.current === 'recording') finish(uri);
    },
    [finish],
  );

  const recorder = useAudioRecorder(CLONE_RECORDING, (status) => {
    if (status.isFinished) ended(status.url);
  });

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      session.current += 1;
      upload.current?.abort();
      if (phaseRef.current === 'idle') return;
      const wasRecording = phaseRef.current === 'recording' || phaseRef.current === 'stopping';
      phaseRef.current = 'idle';
      // The recorder may already be released by now; it stops with it either way.
      try {
        if (wasRecording) recorder.stop().catch(() => {});
      } catch {}
      restorePlayback();
    };
  }, [recorder]);

  const startRecording = useCallback(async () => {
    if (phaseRef.current !== 'idle' || picking.current || uploading.current) return;
    const at = session.current;
    setPhase('starting');
    setError(null);
    player.stop();
    // A later close or unmount owns the audio mode from then on.
    const cancelled = () => {
      if (isLive(at)) return false;
      if (phaseRef.current === 'idle') restorePlayback();
      return true;
    };
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (cancelled()) return;
      if (!permission.granted) {
        setMicDenied(true);
        setPhase('idle');
        return;
      }
      setMicDenied(false);
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (cancelled()) return;
      await recorder.prepareToRecordAsync();
      if (cancelled()) return;
      setRecorded(null);
      startedAt.current = Date.now();
      recorder.record({ forDuration: CLIP_MAX_S });
      setPhase('recording');
    } catch {
      if (cancelled()) return;
      setPhase('idle');
      restorePlayback();
      setError("Couldn't start the microphone. Try again, or choose an audio file instead.");
    }
  }, [isLive, player, recorder, setPhase]);

  // Finalising the file takes a moment: the button shows it's working and can't be tapped twice
  const stopRecording = useCallback(async () => {
    if (phaseRef.current !== 'recording') return;
    const at = session.current;
    setPhase('stopping');
    await recorder.stop().catch(() => {});
    if (isLive(at)) finish(recorder.uri);
  }, [finish, isLive, recorder, setPhase]);

  const pickFile = useCallback(async () => {
    if (phaseRef.current !== 'idle' || picking.current || uploading.current) return;
    picking.current = true;
    const at = session.current;
    setError(null);
    player.stop();
    try {
      const picked = await DocumentPicker.getDocumentAsync({ type: 'audio/*', copyToCacheDirectory: true });
      const asset = picked.canceled ? null : picked.assets[0];
      if (!asset || !isLive(at)) return;
      setRecorded({
        clip: { uri: asset.uri, name: asset.name, mimeType: asset.mimeType ?? 'audio/mpeg' },
        from: 'file',
        seconds: null,
        fileName: asset.name,
      });
    } catch {
      if (isLive(at)) setError("Couldn't open your files. Try again, or record instead.");
    } finally {
      picking.current = false;
    }
  }, [isLive, player]);

  const close = useCallback(() => {
    session.current += 1;
    const was = phaseRef.current;
    if (was === 'recording' || was === 'stopping') recorder.stop().catch(() => {});
    if (was !== 'idle') restorePlayback();
    // A copy still on its way is still added to the list; it just no longer holds the button.
    uploading.current = null;
    player.stop();
    onClose();
    // Start fresh next time.
    setPhase('idle');
    setBusy(false);
    setSlow(false);
    setRecorded(null);
    setVoiceName('');
    setAccent('');
    setConsent(false);
    setMicDenied(false);
    setError(null);
    setMade(null);
  }, [onClose, player, recorder, setPhase]);

  const tooShort = recorded?.seconds !== null && recorded?.seconds !== undefined && recorded.seconds < CLIP_MIN_S;
  const missing = useMemo(
    () =>
      [
        !recorded ? 'a recording' : tooShort ? 'a longer recording' : null,
        voiceName.trim() ? null : 'a name',
        consent ? null : 'their agreement',
      ].filter(Boolean) as string[],
    [recorded, tooShort, voiceName, consent],
  );

  const send = useCallback(async () => {
    if (!recorded || missing.length || uploading.current || phaseRef.current !== 'idle') return;
    const attempt = {};
    uploading.current = attempt;
    const at = session.current;
    player.stop();
    setBusy(true);
    setSlow(false);
    setError(null);
    const abort = new AbortController();
    upload.current = abort;
    const request = cloneVoice(residentId, recorded.clip, voiceName, accent || undefined, abort.signal);
    let slowTimer: ReturnType<typeof setTimeout> | undefined;
    let giveUp: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      slowTimer = setTimeout(() => isLive(at) && setSlow(true), UPLOAD_SLOW_MS);
      giveUp = setTimeout(() => reject(new UploadTimeout()), UPLOAD_TIMEOUT_MS);
    });
    try {
      const voice = await Promise.race([request, timeout]);
      if (mounted.current) onAdded(voice);
      if (isLive(at)) setMade(voice);
    } catch (e) {
      if (e instanceof UploadTimeout) {
        // The copy may still arrive: it exists then, so list it, and show it unless a retry is under way.
        request.then(
          (voice) => {
            if (!mounted.current) return;
            onAdded(voice);
            if (isLive(at) && !uploading.current) {
              setError(null);
              setMade(voice);
            }
          },
          () => {},
        );
      }
      if (isLive(at)) setError(uploadError(e, name));
    } finally {
      clearTimeout(slowTimer);
      clearTimeout(giveUp);
      if (uploading.current === attempt) uploading.current = null;
      if (upload.current === abort) upload.current = null;
      if (isLive(at)) {
        setBusy(false);
        setSlow(false);
      }
    }
  }, [accent, isLive, missing.length, name, onAdded, player, recorded, residentId, voiceName]);

  const listen = useCallback(
    (key: string, load: () => Promise<string>) => {
      if (phaseRef.current !== 'idle') return;
      player.toggle(key, load).catch((e) => mounted.current && setError(previewError(e)));
    },
    [player],
  );

  const accentOptions = useMemo(
    () => [{ value: '', label: 'Not sure' }, ...accents.map((a) => ({ value: a.id, label: a.name }))],
    [accents],
  );

  const isRecording = phase === 'recording' || phase === 'stopping';

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
          {slow
            ? 'Still copying the voice. This can take up to a minute.'
            : 'Sending the recording. This takes a few seconds.'}
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
              <RecordingTimer recorder={recorder} onEnded={ended} />
              <Button
                fullWidth
                title="Stop recording"
                icon={<StopIcon color={colors['on-accent']} size={16} />}
                loading={phase === 'stopping'}
                disabled={phase === 'stopping'}
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
                options={accentOptions}
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

type RecordingTimerProps = {
  recorder: AudioRecorder;
  /** The recorder stopped by itself (it hit CLIP_MAX_S), with where the file is. */
  onEnded: (uri: string | null) => void;
};

/**
 * The running clock, bar and hint while recording. It alone reads the recorder every TICK_MS, and
 * only while it is shown, so the rest of the sheet doesn't redraw on each tick. Also notices when
 * the recorder stops by itself, in case its finished event never comes.
 */
const RecordingTimer = memo(function RecordingTimer({ recorder, onEnded }: RecordingTimerProps) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    let started = false;
    const tick = setInterval(() => {
      let status;
      try {
        status = recorder.getStatus();
      } catch {
        return;
      }
      if (status.isRecording) {
        started = true;
        setSeconds(status.durationMillis / 1000);
      } else if (started) {
        started = false;
        onEnded(status.url ?? recorder.uri);
      }
    }, TICK_MS);
    return () => clearInterval(tick);
  }, [recorder, onEnded]);

  return (
    <>
      <View className="flex-row items-baseline gap-2">
        <Text className="font-display text-3xl text-ink" style={{ fontVariant: ['tabular-nums'] }}>
          {clock(seconds)}
        </Text>
        <Text className="font-sans text-sm text-ink-muted">of {clock(CLIP_MAX_S)}, recording</Text>
      </View>
      <TimerBar seconds={seconds} />
      <Text className="font-sans text-sm text-ink-muted">
        {seconds < CLIP_MIN_S
          ? `Keep going: at least ${CLIP_MIN_S} seconds.`
          : 'That is enough. Stop whenever you are ready.'}
      </Text>
    </>
  );
});

/** How far into the recording's CLIP_MAX_S it is, with a mark where it becomes long enough. */
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
