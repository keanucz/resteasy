import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, Text, type TextInputProps, View } from 'react-native';
import Animated, { FadeIn, FadeOut, ReduceMotion } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/Button';
import { Dialog, type Status, StatusLine } from '@/components/Feedback';
import { List, ListRow } from '@/components/List';
import { PeopleList } from '@/components/PeoplePicker';
import { PhotoRing } from '@/components/PhotoRing';
import { SegmentedTabs, Toggle } from '@/components/Selection';
import { TextField } from '@/components/TextField';
import { useSwitchScheme } from '@/components/ThemeBubble';
import { TimeSelect } from '@/components/TimeSelect';
import { VoicePicker } from '@/components/VoicePicker';
import { DURATION, EASE } from '@/constants/motion';
import { CHECKIN_MAX_WAIT, CHECKIN_MIN_WAIT, SAVED_NOTE_MS } from '@/constants/pillow';
import { type Resident, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { setResidentPhoto, useResidentPhoto } from '@/hooks/useResidentPhoto';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';
import { api, ApiError } from '@/services/api';
import { signOut } from '@/services/auth';
import { isTestAccount, SIMULATED_ALERTS, type SimulatedAlert, simulateAlert } from '@/services/debug';
import { pickAndUploadPhoto } from '@/services/photo';
import { supabase } from '@/services/supabase/client';

/** What the pillow learned from her past week (backend PR #47); absent on older backends. */
type Baseline = {
  mode: 'learned' | 'learning';
  usual_trip_min: number | null;
  learned_timeout_min: number | null;
  checkin_timeout_min: number;
};

/** The wait the pillow really uses, which is shorter than the chosen one once it knows her usual trips. */
function baselineLine(baseline: Baseline | null, chosen: number | undefined, name: string): string | null {
  if (!baseline) return null;
  if (baseline.mode === 'learning') return `Still learning ${name}'s usual night, so it waits as long as you choose.`;
  if (chosen !== undefined && baseline.checkin_timeout_min >= chosen) return null;
  return `It checks after ${baseline.checkin_timeout_min} min for now: ${name}'s usual trip is up to ${baseline.usual_trip_min} min.`;
}

type Preferences = Pick<Resident, 'quiet_start' | 'quiet_end' | 'checkin_timeout_min' | 'monitoring_paused'>;

/** Which setting a save belongs to, so its result shows next to that control. */
type StatusKey = 'quiet' | 'wait' | 'pause';

const SCHEMES = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
] as const;

const WAIT_INVALID = `Between ${CHECKIN_MIN_WAIT} and ${CHECKIN_MAX_WAIT} minutes`;

/**
 * Where a change is saved. Watching hours and the check-in wait belong to the person, so they go to
 * the resident's own endpoints (both times together); the rest goes through the pillow's preferences.
 */
function saveRequest(
  key: StatusKey,
  patch: Partial<Preferences>,
  next: Preferences,
  pillowId: string,
  residentId: string | null,
): [string, { method: 'PUT' | 'PATCH'; body: object }] {
  if (residentId && key === 'quiet') {
    return [
      `/residents/${residentId}/watch-hours`,
      { method: 'PUT', body: { quiet_start: next.quiet_start, quiet_end: next.quiet_end } },
    ];
  }
  if (residentId && key === 'wait') {
    return [
      `/residents/${residentId}/checkin-wait`,
      { method: 'PUT', body: { checkin_timeout_min: next.checkin_timeout_min } },
    ];
  }
  return [`/pillows/${pillowId}/preferences`, { method: 'PATCH', body: patch }];
}

/** Why a save failed, in words the family member can act on. */
function saveError(e: unknown): string {
  if (e instanceof ApiError && e.status === 403)
    return "You're not in this pillow's care circle, so you can't change it.";
  if (e instanceof ApiError && e.status === 404) return "The pillow can't take changes from the app yet.";
  if (e instanceof ApiError && e.status === 422) return "The pillow didn't accept that value.";
  return "Couldn't save that. Check your connection and try again.";
}

/** Reads the typed wait (digits only) in minutes, or null when it's outside what the pillow allows. */
function parseWait(input: string): number | null {
  if (!/^\d+$/.test(input)) return null;
  const minutes = Number(input);
  return minutes >= CHECKIN_MIN_WAIT && minutes <= CHECKIN_MAX_WAIT ? minutes : null;
}

/**
 * Settings: how the pillow behaves for her (voice, when it watches, how long it waits before
 * telling family), then this phone (light or dark), then the account.
 */
export default function SettingsScreen() {
  const { pillowId, people, disconnect } = usePillowLink();
  const residentId = usePillow().resident?.id ?? null;
  const { session } = useSession();
  const { scheme } = useTheme();
  const switchScheme = useSwitchScheme();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [name, setName] = useState('your parent');
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [statuses, setStatuses] = useState<Record<StatusKey, Status | null>>({
    quiet: null,
    wait: null,
    pause: null,
  });
  const [confirm, setConfirm] = useState<'pause' | 'disconnect' | null>(null);

  // The latest preferences, so save() can stay the same function across renders.
  const prefsRef = useRef<Preferences | null>(null);
  const timers = useRef<Partial<Record<StatusKey, ReturnType<typeof setTimeout>>>>({});

  const commitPrefs = useCallback((next: Preferences) => {
    prefsRef.current = next;
    setPrefs(next);
  }, []);

  /** Shows a save's result next to its control; "Saved" clears itself after a moment. */
  const showStatus = useCallback((key: StatusKey, status: Status | null) => {
    clearTimeout(timers.current[key]);
    setStatuses((all) => ({ ...all, [key]: status }));
    if (status?.kind === 'saved') {
      timers.current[key] = setTimeout(() => setStatuses((all) => ({ ...all, [key]: null })), SAVED_NOTE_MS);
    }
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => Object.values(pending).forEach(clearTimeout);
  }, []);

  useEffect(() => {
    if (!pillowId) return;
    supabase
      .from('pillows')
      .select('residents(preferred_name, quiet_start, quiet_end, checkin_timeout_min, monitoring_paused)')
      .eq('id', pillowId)
      .maybeSingle()
      .then(({ data }) => {
        const resident = data?.residents as unknown as (Preferences & { preferred_name: string }) | null;
        if (!resident) return;
        // Times come back as "HH:MM:SS"; keep them as "HH:MM", the shape the app sends.
        commitPrefs({
          quiet_start: resident.quiet_start.slice(0, 5),
          quiet_end: resident.quiet_end.slice(0, 5),
          checkin_timeout_min: resident.checkin_timeout_min,
          monitoring_paused: resident.monitoring_paused,
        });
        setName(resident.preferred_name);
      });
    api<{ summary: { baseline?: Baseline } }>(`/pillows/${pillowId}/night`).then(
      (night) => setBaseline(night.summary.baseline ?? null),
      () => setBaseline(null),
    );
  }, [pillowId, commitPrefs]);

  /** Show the change at once, then save it; put those settings back if the save fails. */
  const save = useCallback(
    async (patch: Partial<Preferences>, key: StatusKey) => {
      const current = prefsRef.current;
      if (!pillowId || !current) return;
      const keys = Object.keys(patch) as (keyof Preferences)[];
      if (keys.every((k) => current[k] === patch[k])) return;
      const before = Object.fromEntries(keys.map((k) => [k, current[k]])) as Partial<Preferences>;
      commitPrefs({ ...current, ...patch });
      showStatus(key, null);
      try {
        const next = { ...current, ...patch };
        await api(...saveRequest(key, patch, next, pillowId, residentId));
        showStatus(key, { kind: 'saved', text: 'Saved' });
      } catch (e) {
        if (prefsRef.current) commitPrefs({ ...prefsRef.current, ...before });
        showStatus(key, { kind: 'error', text: saveError(e) });
      }
    },
    [pillowId, residentId, commitPrefs, showStatus],
  );

  const saveFrom = useCallback((quiet_start: string) => save({ quiet_start }, 'quiet'), [save]);
  const saveUntil = useCallback((quiet_end: string) => save({ quiet_end }, 'quiet'), [save]);
  const saveWait = useCallback((checkin_timeout_min: number) => save({ checkin_timeout_min }, 'wait'), [save]);
  const setPaused = useCallback(
    (paused: boolean) => (paused ? setConfirm('pause') : save({ monitoring_paused: false }, 'pause')),
    [save],
  );

  const waitNote = baselineLine(baseline, prefs?.checkin_timeout_min, name);

  return (
    <View className="flex-1 bg-canvas">
      <SafeAreaView edges={['top']} style={{ flex: 1 }}>
        <ScrollView
          contentContainerClassName="gap-8 px-4 pb-10 pt-6"
          keyboardDismissMode="on-drag"
          automaticallyAdjustKeyboardInsets
        >
          <Text accessibilityRole="header" className="font-display text-3xl text-ink">
            Settings
          </Text>

          {people.length > 1 ? (
            <Section title="People you look after" note="Tap someone to see their nights. Settings below are theirs.">
              <PeopleList />
            </Section>
          ) : null}

          <PhotoSection name={name} />

          <Section title="Voice" note={`What ${name}'s pillow sounds like, for reminders, check-ins and goodnight.`}>
            <VoicePicker name={name} />
          </Section>

          <Section
            title="When it watches"
            note={`Evening to morning on ${name}'s clock. Outside these hours the pillow stays quiet. Same time in both means it watches all day.`}
          >
            <View className="flex-row gap-3">
              <View className="flex-1">
                <TimeSelect label="From" value={prefs?.quiet_start} onChange={saveFrom} />
              </View>
              <View className="flex-1">
                <TimeSelect label="Until" value={prefs?.quiet_end} onChange={saveUntil} />
              </View>
            </View>
            <StatusLine status={statuses.quiet} />
          </Section>

          <Section title="Before telling family" note={`The longest ${name} can be up before the pillow checks in.`}>
            <View className="w-1/2 pr-1.5">
              <DraftField
                label="Minutes"
                saved={prefs?.checkin_timeout_min}
                parse={parseWait}
                format={String}
                invalid={WAIT_INVALID}
                onCommit={saveWait}
                editable={prefs !== null}
                placeholder="15"
                digitsOnly
                maxLength={2}
                keyboardType="number-pad"
                returnKeyType="done"
                accessibilityHint={WAIT_INVALID}
              />
            </View>
            {waitNote ? <Text className="font-sans text-sm text-ink-muted">{waitNote}</Text> : null}
            <StatusLine status={statuses.wait} />
          </Section>

          <View className="gap-3">
            <List>
              <ListRow
                title="Pause watching"
                onPress={() => setPaused(!prefs?.monitoring_paused)}
                meta={
                  prefs?.monitoring_paused
                    ? `Paused. Nobody will be told if ${name} gets up.`
                    : `For nights ${name} is away from home.`
                }
                trailing={
                  <Toggle label="Pause watching" value={prefs?.monitoring_paused ?? false} onValueChange={setPaused} />
                }
              />
            </List>
            <StatusLine status={statuses.pause} />
          </View>

          <AlertDebugSection pillowId={pillowId} />

          <Section title="This phone">
            <SegmentedTabs options={SCHEMES} value={scheme} onChange={switchScheme} />
          </Section>

          <Section title="Account" note={session?.user.email ? `Logged in as ${session.user.email}` : undefined}>
            <View className="gap-4">
              <Button
                fullWidth
                variant="secondary"
                title="Disconnect pillow"
                onPress={() => setConfirm('disconnect')}
              />
              <Button fullWidth variant="ghost" title="Log out" onPress={signOut} />
            </View>
          </Section>
        </ScrollView>
        <Dialog
          visible={confirm === 'pause'}
          title="Pause watching?"
          body={`Nobody will be told if ${name} gets up and doesn't come back, until you turn it on again.`}
          confirmLabel="Pause watching"
          danger
          onConfirm={() => {
            setConfirm(null);
            save({ monitoring_paused: true }, 'pause');
          }}
          onCancel={() => setConfirm(null)}
        />
        <Dialog
          visible={confirm === 'disconnect'}
          title="Disconnect the pillow?"
          body={`This phone stops showing ${name}'s nights. The pillow keeps watching, and you can connect again any time.`}
          confirmLabel="Disconnect"
          onConfirm={() => {
            setConfirm(null);
            disconnect();
          }}
          onCancel={() => setConfirm(null)}
        />
      </SafeAreaView>
    </View>
  );
}

/** Her photo, shown in the sky's ring on Tonight. Anyone in the care circle may change it (storage policy). */
function PhotoSection({ name }: { name: string }) {
  const { resident } = usePillow();
  const residentId = resident?.id ?? null;
  const photo = useResidentPhoto(residentId);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  const choose = async () => {
    if (!residentId) return;
    setBusy(true);
    setStatus(null);
    try {
      const url = await pickAndUploadPhoto(residentId);
      if (url) {
        setResidentPhoto(residentId, url);
        setStatus({ kind: 'saved', text: 'Saved' });
      }
    } catch (e) {
      setStatus({ kind: 'error', text: e instanceof Error ? e.message : "Couldn't upload the photo. Try again." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="Photo" note={`Shown at the top of Tonight, so you see ${name} first.`}>
      <View className="flex-row items-center gap-4 rounded-2xl bg-surface p-3.5">
        <PhotoRing state="asleep" initials={name.slice(0, 1).toUpperCase()} photoUri={photo ?? undefined} size={72} />
        <View className="flex-1">
          <Button
            variant="secondary"
            title={photo ? 'Change photo' : 'Add a photo'}
            loading={busy}
            disabled={!residentId}
            onPress={choose}
          />
        </View>
      </View>
      <StatusLine status={status} />
    </Section>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <View className="gap-3">
      <View className="gap-1">
        <Text accessibilityRole="header" className="font-display text-xl text-ink">
          {title}
        </Text>
        {note ? <Text className="font-sans text-sm text-ink-muted">{note}</Text> : null}
      </View>
      {children}
    </View>
  );
}

type DraftFieldProps<T> = Pick<
  TextInputProps,
  | 'placeholder'
  | 'editable'
  | 'keyboardType'
  | 'returnKeyType'
  | 'autoCapitalize'
  | 'autoCorrect'
  | 'accessibilityHint'
  | 'maxLength'
> & {
  /** Drops anything but 0-9 as it is typed, so only a number can go in. */
  digitsOnly?: boolean;
  label: string;
  /** The saved value; the field shows it formatted and follows it when it changes (load, or a failed save put back). */
  saved: T | undefined;
  parse: (text: string) => T | null;
  format: (value: T) => string;
  /** Shown under the field when the typed text doesn't parse. */
  invalid: string;
  onCommit: (value: T) => void;
};

/**
 * A field the family types into freely; it only saves when they finish (blur, which a submit also
 * causes). Bad input stays in the field with its message underneath and nothing is saved. The
 * message line is always reserved, so it never pushes the page.
 */
function DraftField<T>({ label, saved, parse, format, invalid, onCommit, digitsOnly, ...input }: DraftFieldProps<T>) {
  const { colors } = useTheme();
  const shown = saved === undefined ? '' : format(saved);
  const [text, setText] = useState(shown);
  const [error, setError] = useState<string | null>(null);
  const [lastShown, setLastShown] = useState(shown);
  if (shown !== lastShown) {
    setLastShown(shown);
    setText(shown);
    setError(null);
  }

  const commit = () => {
    const value = parse(text);
    if (value === null) {
      setError(invalid);
      return;
    }
    setError(null);
    setText(format(value));
    onCommit(value);
  };

  return (
    <View className="gap-1">
      {/* No error prop: TextField adds its message line only when there is one, which would shift
          the page. The border is set here instead and the line below is always reserved. */}
      <TextField
        label={label}
        value={text}
        onChangeText={(typed) => {
          const next = digitsOnly ? typed.replace(/\D/g, '') : typed;
          setText(next);
          if (error) setError(null);
        }}
        onBlur={commit}
        style={error ? { borderColor: colors.danger } : undefined}
        {...input}
      />
      <View className="min-h-4 justify-center">
        {error ? (
          <Animated.View
            entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
            exiting={FadeOut.duration(DURATION.exit).easing(EASE.in).reduceMotion(ReduceMotion.System)}
          >
            <Text accessibilityLiveRegion="polite" className="font-sans text-xs text-danger-text">
              {error}
            </Text>
          </Animated.View>
        ) : null}
      </View>
    </View>
  );
}

/**
 * Test accounts only (contacts.is_test in Supabase): plays an alert on the pillow, one rung at a
 * time, so the app's alert screens can be tried without anyone getting out of bed. The database
 * refuses other accounts, and nobody is called or texted.
 */
function AlertDebugSection({ pillowId }: { pillowId: string | null }) {
  const [allowed, setAllowed] = useState(false);
  const [busy, setBusy] = useState<SimulatedAlert | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    let cancelled = false;
    isTestAccount().then((yes) => {
      if (!cancelled) setAllowed(yes);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!allowed || !pillowId) return null;

  const play = async (level: SimulatedAlert) => {
    setBusy(level);
    setStatus(null);
    try {
      setStatus({ kind: 'saved', text: await simulateAlert(pillowId, level) });
    } catch (e) {
      setStatus({ kind: 'error', text: e instanceof Error ? e.message : "Couldn't play that alert." });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Section
      title="Alert debug"
      note="Test account only. Plays an alert on this pillow as if it happened now, in the order a real night climbs. Nobody is called or texted."
    >
      <View className="flex-row flex-wrap gap-2.5">
        {SIMULATED_ALERTS.map((a) => (
          <View key={a.level} className="min-w-[46%] flex-1">
            <Button
              fullWidth
              variant={a.level === 'clear' ? 'ghost' : 'secondary'}
              title={a.label}
              loading={busy === a.level}
              disabled={busy !== null && busy !== a.level}
              onPress={() => play(a.level)}
            />
          </View>
        ))}
      </View>
      <StatusLine status={status} />
    </Section>
  );
}
