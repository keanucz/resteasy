import { memo, useCallback, useEffect, useRef, useState } from 'react';
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

/** The preferences behind each status line: saved together, and put back together when a save fails. */
const FIELDS: Record<StatusKey, (keyof Preferences)[]> = {
  quiet: ['quiet_start', 'quiet_end'],
  wait: ['checkin_timeout_min'],
  pause: ['monitoring_paused'],
};

/** How long a setting waits for more changes before saving, so a burst of taps sends one request. */
const SAVE_DELAY_MS = 500;

const SAVED: Status = { kind: 'saved', text: 'Saved' };
const NO_STATUS: Record<StatusKey, Status | null> = { quiet: null, wait: null, pause: null };

/**
 * One setting's save: the timer while changes may still come, whether a request is out, and
 * where it goes (fixed when the change was made, so it can't land on another person's pillow).
 */
type Saving = {
  timer?: ReturnType<typeof setTimeout>;
  busy: boolean;
  target?: { pillowId: string; residentId: string | null };
  /** Settings changed while a request was out and the screen moved on: sent once that one is back. */
  last?: Preferences;
};

const newSaves = (): Record<StatusKey, Saving> => ({ quiet: { busy: false }, wait: { busy: false }, pause: { busy: false } });

/** The part of `prefs` that `key` covers. */
function part(prefs: Preferences, key: StatusKey): Partial<Preferences> {
  return Object.fromEntries(FIELDS[key].map((k) => [k, prefs[k]])) as Partial<Preferences>;
}

/** Whether `a` and `b` agree on everything `key` covers. */
const same = (a: Preferences, b: Preferences, key: StatusKey) => FIELDS[key].every((k) => a[k] === b[k]);

/** The settings as the resident's record has them; times trimmed from "HH:MM:SS" to "HH:MM", the shape the app sends. */
function fromRecord(r: Preferences): Preferences {
  return {
    quiet_start: r.quiet_start.slice(0, 5),
    quiet_end: r.quiet_end.slice(0, 5),
    checkin_timeout_min: r.checkin_timeout_min,
    monitoring_paused: r.monitoring_paused,
  };
}

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
  return [`/pillows/${pillowId}/preferences`, { method: 'PATCH', body: part(next, key) }];
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
  const { resident } = usePillow();
  const residentId = resident?.id ?? null;
  const { session } = useSession();
  const { scheme } = useTheme();
  const switchScheme = useSwitchScheme();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [loadedName, setLoadedName] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [baseline, setBaseline] = useState<Baseline | null>(null);
  const [statuses, setStatuses] = useState<Record<StatusKey, Status | null>>(NO_STATUS);
  const [confirm, setConfirm] = useState<'pause' | 'disconnect' | null>(null);
  const name = loadedName ?? resident?.preferred_name ?? 'your parent';

  // What the screen shows (the latest choices) and what the backend has, read by saves without re-rendering.
  const prefsRef = useRef<Preferences | null>(null);
  const serverRef = useRef<Preferences | null>(null);
  // Settings changed here: a read that comes back later never replaces them.
  const touched = useRef(new Set<StatusKey>());
  const saves = useRef(newSaves());
  const timers = useRef<Partial<Record<StatusKey, ReturnType<typeof setTimeout>>>>({});

  const commitPrefs = useCallback((next: Preferences | null) => {
    prefsRef.current = next;
    setPrefs(next);
  }, []);

  /** Takes settings read from the backend, keeping any the family has changed here since. */
  const applyLoaded = useCallback(
    (fresh: Preferences) => {
      const shown = prefsRef.current;
      const server = serverRef.current;
      let next = fresh;
      let known = fresh;
      for (const key of touched.current) {
        if (shown) next = { ...next, ...part(shown, key) };
        if (server) known = { ...known, ...part(server, key) };
      }
      serverRef.current = known;
      commitPrefs(next);
    },
    [commitPrefs],
  );

  /** Shows a save's result next to its control; "Saved" clears itself after a moment. */
  const showStatus = useCallback((key: StatusKey, status: Status | null) => {
    clearTimeout(timers.current[key]);
    setStatuses((all) => (all[key] === status ? all : { ...all, [key]: status }));
    if (status?.kind === 'saved') {
      timers.current[key] = setTimeout(() => setStatuses((all) => ({ ...all, [key]: null })), SAVED_NOTE_MS);
    }
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => Object.values(pending).forEach(clearTimeout);
  }, []);

  /**
   * Sends `key`'s settings as they are now. Only one request per setting is out at a time: a
   * change made meanwhile is sent after it, so the newest choice always lands last. A failure puts
   * the setting back as the backend has it, unless a newer change is already on its way.
   */
  const send = useCallback(
    async (key: StatusKey) => {
      const run = saves.current;
      const save = run[key];
      clearTimeout(save.timer);
      save.timer = undefined;
      if (save.busy || !save.target) return;
      const { pillowId: pid, residentId: rid } = save.target;
      save.busy = true;
      try {
        for (;;) {
          const next = prefsRef.current;
          const server = serverRef.current;
          if (!next || !server || same(next, server, key)) return;
          try {
            await api(...saveRequest(key, next, pid, rid));
            if (saves.current !== run) return;
            serverRef.current = { ...(serverRef.current ?? next), ...part(next, key) };
            if (!save.timer && prefsRef.current && same(prefsRef.current, next, key)) {
              showStatus(key, SAVED);
              return;
            }
          } catch (e) {
            if (saves.current !== run) return;
            if (!save.timer && prefsRef.current && same(prefsRef.current, next, key)) {
              commitPrefs({ ...prefsRef.current, ...part(serverRef.current ?? next, key) });
              showStatus(key, { kind: 'error', text: saveError(e) });
              return;
            }
          }
          // A newer change still waiting for its timer is sent when that fires.
          if (save.timer) return;
        }
      } finally {
        save.busy = false;
        const last = save.last;
        save.last = undefined;
        if (last && saves.current !== run) void api(...saveRequest(key, last, pid, rid)).catch(() => {});
      }
    },
    [commitPrefs, showStatus],
  );

  // Leaving this pillow (another person, or the screen closing) sends what is still waiting, then
  // forgets this pillow's settings so the next one's never show them.
  useEffect(() => {
    if (!pillowId) return;
    let cancelled = false;
    api<{ summary: { baseline?: Baseline } }>(`/pillows/${pillowId}/night`).then(
      (night) => {
        if (!cancelled) setBaseline(night.summary.baseline ?? null);
      },
      () => {
        if (!cancelled) setBaseline(null);
      },
    );
    return () => {
      cancelled = true;
      const run = saves.current;
      (Object.keys(run) as StatusKey[]).forEach((key) => {
        if (!run[key].timer) return;
        if (run[key].busy && prefsRef.current) {
          clearTimeout(run[key].timer);
          run[key].last = prefsRef.current;
        } else send(key);
      });
      saves.current = newSaves();
      touched.current = new Set();
      serverRef.current = null;
      commitPrefs(null);
      setLoadedName(null);
      setBaseline(null);
      setStatuses(NO_STATUS);
    };
  }, [pillowId, send, commitPrefs]);

  // Shows what the app already knows about her at once, before the fresh read below arrives.
  useEffect(() => {
    if (resident && !prefsRef.current) applyLoaded(fromRecord(resident));
  }, [resident, applyLoaded]);

  useEffect(() => {
    if (!pillowId) return;
    let cancelled = false;
    supabase
      .from('pillows')
      .select('residents(preferred_name, quiet_start, quiet_end, checkin_timeout_min, monitoring_paused)')
      .eq('id', pillowId)
      .maybeSingle()
      .then(
        ({ data }) => {
          if (cancelled) return;
          const found = data?.residents as unknown as (Preferences & { preferred_name: string }) | null;
          setLoadFailed(!found);
          if (!found) return;
          applyLoaded(fromRecord(found));
          setLoadedName(found.preferred_name);
        },
        () => {
          if (!cancelled) setLoadFailed(true);
        },
      );
    return () => {
      cancelled = true;
    };
  }, [pillowId, attempt, applyLoaded]);

  /** Show the change at once, then save it once the family stops changing that setting for a moment. */
  const save = useCallback(
    (patch: Partial<Preferences>, key: StatusKey) => {
      const current = prefsRef.current;
      if (!pillowId || !current) return;
      const keys = Object.keys(patch) as (keyof Preferences)[];
      if (keys.every((k) => current[k] === patch[k])) return;
      commitPrefs({ ...current, ...patch });
      touched.current.add(key);
      showStatus(key, null);
      const pending = saves.current[key];
      pending.target = { pillowId, residentId };
      clearTimeout(pending.timer);
      pending.timer = setTimeout(() => send(key), SAVE_DELAY_MS);
    },
    [pillowId, residentId, commitPrefs, showStatus, send],
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

          {loadFailed && !prefs ? (
            <View className="items-start gap-2">
              <Text accessibilityLiveRegion="polite" className="font-sans text-sm text-danger-text">
                Couldn&apos;t load {name}&apos;s settings. Check your connection and try again.
              </Text>
              <Button variant="ghost" title="Try again" onPress={() => setAttempt((a) => a + 1)} />
            </View>
          ) : null}

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
const PhotoSection = memo(function PhotoSection({ name }: { name: string }) {
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
});

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
const AlertDebugSection = memo(function AlertDebugSection({ pillowId }: { pillowId: string | null }) {
  const [allowed, setAllowed] = useState(false);
  const [busy, setBusy] = useState<SimulatedAlert | null>(null);
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    let cancelled = false;
    isTestAccount().then(
      (yes) => {
        if (!cancelled) setAllowed(yes);
      },
      () => {
        // Not knowing means not a test account: the section just stays hidden.
      },
    );
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
});
