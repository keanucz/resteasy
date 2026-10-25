import { router } from 'expo-router';
import { memo, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { hm, type WeekBar, WeekSleepChart } from '@/components/Charts';
import { NotificationCard } from '@/components/Feedback';
import { Hills } from '@/components/Hills';
import { List, ListRow } from '@/components/List';
import { NightDetail } from '@/components/NightDetail';
import { PeopleSheet } from '@/components/PeoplePicker';
import { SkyHeader } from '@/components/SkyHeader';
import { DataTable, StatTile } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { BellIcon, PhoneIcon, PillIcon } from '@/components/TabIcons';
import { ALERT_ENDED_NOTICE_MS, MONTH_NIGHTS, RIBBON_HOURS, WEEK_NIGHTS } from '@/constants/pillow';
import { tapAllClear, useAlertBuzz } from '@/hooks/useAlertBuzz';
import { useAlertPrefs } from '@/hooks/useAlertPrefs';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useGuardedPress } from '@/hooks/useGuardedPress';
import { useNow, usePillow, usePillowState } from '@/hooks/usePillow';
import { usePillowCheck } from '@/hooks/usePillowCheck';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useResidentPhoto } from '@/hooks/useResidentPhoto';
import { useTheme } from '@/hooks/useTheme';
import { api } from '@/services/api';
import {
  appState,
  clockTime,
  type EventRow,
  formatter,
  type IncidentRow,
  isFlagged,
  latestNight,
  nightFacts,
  nightTitle,
  type NightWindow,
  ribbonNow,
  type ReminderToday,
  shortDay,
  sleptMinutes,
  stateDetail,
  todaysReminders,
  weekSummaries,
} from '@/services/night';

/** What happened to today's reminder: a word, coloured only when it went well or needs a look. */
const REMINDER_WORD: Record<ReminderToday['status'], { word: string; state?: 'asleep' | 'up' }> = {
  later: { word: 'Later' },
  waiting: { word: 'Waiting' },
  due: { word: 'Reminding' },
  announced: { word: 'Reminded' },
  done: { word: 'Done', state: 'asleep' },
  missed: { word: 'Not confirmed', state: 'up' },
};

/** How long "I'm on it" waits for the alert to say someone is on it before asking for another tap. */
const ACK_CONFIRM_MS = 15_000;

/** How an alert ended, as the card on Tonight says it. */
const ENDED_TITLE: Record<NonNullable<IncidentRow['resolved_reason']>, (name: string) => string> = {
  fine: (name) => `${name} said "I'm fine"`,
  back_in_bed: (name) => `${name} is back in bed`,
  cleared: () => 'The alert is over',
};

const openNight = (start: number) => router.push({ pathname: '/night/[start]', params: { start: String(start) } });

/**
 * `night`, or the last one returned while it is the same night: a fresh window comes back on every
 * tick, and everything worked out from it only needs doing again when the night itself changes.
 */
function useSameNight(night: NightWindow): NightWindow {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => night, [night.start, night.over]);
}

/**
 * Tonight: the sky says how she is (and the hedgehog keeps her company on the arch), then anything
 * that needs you and today's reminders, then the latest night in full, the week and the month as
 * sleep charts, and the nights one by one. Tap a night in a chart or the list to open it.
 */
export default function TonightScreen() {
  const { pillowId, people, contactId } = usePillowLink();
  const alertPrefs = useAlertPrefs(contactId);
  const pillow = usePillow();
  const { events, incidents } = pillow;
  const [picking, setPicking] = useState(false);
  const now = useNow();
  const showSkeleton = useDelayedLoading(pillow.loading);
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';
  const name = pillow.resident?.preferred_name ?? 'Mum';

  const night = useSameNight(latestNight(events, now, tz));
  const title = nightTitle(night, now, tz);
  const week = useMemo(() => weekSummaries(events, incidents, night, WEEK_NIGHTS, tz, name), [events, incidents, night, tz, name]);
  const reminders = useMemo(
    () => todaysReminders(pillow.reminders, pillow.occurrences, now, tz),
    [pillow.reminders, pillow.occurrences, now, tz],
  );
  // Only the newest alert can be in progress: an older one still marked open lost its ladder (the
  // backend now clears those, this guards rows left from before).
  const live = useMemo(() => {
    const newest = incidents.reduce<IncidentRow | undefined>(
      (best, i) => (!best || Date.parse(i.opened_at) > Date.parse(best.opened_at) ? i : best),
      undefined,
    );
    return newest && (newest.status === 'open' || newest.status === 'acknowledged') ? newest : undefined;
  }, [incidents]);
  // An alert that just ended with a reason worth telling (she said she's fine, she's back in bed),
  // until it's dismissed or a while has passed.
  const [dismissed, setDismissed] = useState<ReadonlySet<number>>(() => new Set());
  const ended = useMemo(
    () =>
      live
        ? undefined
        : incidents.find(
            (i) =>
              i.status === 'resolved' &&
              i.resolved_reason &&
              i.resolved_at &&
              now - Date.parse(i.resolved_at) < ALERT_ENDED_NOTICE_MS &&
              !dismissed.has(i.id),
          ),
    [live, incidents, now, dismissed],
  );
  const endedId = ended?.id;
  useEffect(() => {
    if (endedId !== undefined) tapAllClear();
  }, [endedId]);
  // This phone buzzes while an alert is open, until someone (this person, the moment they tap) is on it.
  const [tappedOnIt, setTappedOnIt] = useState<number | null>(null);
  const liveId = live?.id ?? null;
  const markTapped = useCallback((tapped: boolean) => setTappedOnIt(tapped ? liveId : null), [liveId]);
  useAlertBuzz(live?.status === 'open' && live.id !== tappedOnIt && (alertPrefs?.app ?? true));

  // A quick second tap on a night (or on another one) is dropped, so a night never opens twice.
  const { press: open } = useGuardedPress(openNight);
  const bars: WeekBar[] = useMemo(
    () =>
      [...week].reverse().map((n) => {
        const minutes = sleptMinutes(events, n.window);
        return {
          key: n.key,
          label: shortDay(n.window, tz),
          hours: minutes ? minutes / 60 : null,
          flagged: isFlagged(n.tone),
          onPress: () => open(n.key),
        };
      }),
    [week, events, tz, open],
  );
  const facts = useMemo(() => week.map((n) => nightFacts(events, n.window, tz)), [week, events, tz]);
  const month = useMemo(() => monthOverview(events, incidents, night, tz, name), [events, incidents, night, tz, name]);
  const monthBars = useMemo(() => month.bars.map((b) => ({ ...b, onPress: () => open(b.key) })), [month, open]);
  const rows = useMemo(
    () =>
      week.map((n, i) => [
        shortDay(n.window, tz),
        facts[i].inBed ?? '–',
        // Getting up once is ordinary: the word only turns amber on a night the charts flag.
        facts[i].trips && isFlagged(n.tone) ? (
          <Text key="up" className="text-sm">
            <StatusWord state="up">{facts[i].tripsWord}</StatusWord>
          </Text>
        ) : facts[i].trips ? (
          <Text key="up" className="font-sans text-sm text-ink">
            {facts[i].tripsWord}
          </Text>
        ) : (
          <Text key="no" className="font-sans text-sm text-ink-muted">
            {facts[i].inBed ? 'No' : '–'}
          </Text>
        ),
        facts[i].woke ?? '–',
      ]),
    [week, facts, tz],
  );
  const onRowPress = useCallback((i: number) => open(week[i].key), [open, week]);
  const rowLabel = useCallback((i: number) => `${week[i].title}: ${week[i].line} Open the night.`, [week]);
  const switchPerson = useCallback(() => setPicking(true), []);
  const closePicker = useCallback(() => setPicking(false), []);

  return (
    <ScrollView
      className="flex-1 bg-canvas"
      refreshControl={<RefreshControl refreshing={false} onRefresh={pillow.refresh} />}
    >
      <TonightSky
        pillowId={pillowId}
        residentId={pillow.resident?.id ?? null}
        name={name}
        night={night}
        events={events}
        live={live ?? null}
        contactId={contactId}
        tz={tz}
        loading={pillow.loading}
        onSwitchPerson={people.length > 1 ? switchPerson : undefined}
      />
      <View className="-mt-2 gap-8 px-4">
        {pillow.error ? (
          <Text accessibilityLiveRegion="polite" className="font-sans text-sm text-danger-text">
            {pillow.error}
          </Text>
        ) : null}
        {live && pillowId ? (
          <AlertCard
            key={live.id}
            pillowId={pillowId}
            name={name}
            incident={live}
            tz={tz}
            onTapped={markTapped}
          />
        ) : null}
        {ended?.resolved_reason && ended.resolved_at ? (
          // Said out loud too: a screen reader hears that the alert ended without looking for it.
          <View accessibilityLiveRegion="polite">
            <NotificationCard
              initials={name.slice(0, 1)}
              title={ENDED_TITLE[ended.resolved_reason](name)}
              detail="Tap to dismiss."
              time={clockTime(ended.resolved_at, tz)}
              onPress={() => setDismissed((d) => new Set(d).add(ended.id))}
            />
          </View>
        ) : null}

        {reminders.length ? (
          <Section title="Reminders today">
            <List>
              {reminders.map((r) => (
                <ListRow
                  key={r.key}
                  leading={<ReminderIcon kind={r.kind} />}
                  title={r.label}
                  meta={`${r.time}${r.confirm ? `, ${name} confirms` : ''}`}
                  trailing={<Word {...REMINDER_WORD[r.status]} />}
                />
              ))}
            </List>
          </Section>
        ) : null}

        <Section title={title}>
          <NightDetail night={night} title={title} showSkeleton={showSkeleton} />
        </Section>

        <Section title={night.over ? 'Earlier this week' : 'This week'}>
          <WeekSleepChart title="Sleep each night" bars={bars} />
        </Section>

        <Section title="Past four weeks">
          <View className="flex-row gap-2.5">
            <StatTile label="Average sleep" value={month.averageSleep} />
            <StatTile label="Up a night" value={month.tripsPerNight} />
            <StatTile label="Alerts" value={month.alerts} />
          </View>
          <WeekSleepChart title="Sleep, last 28 nights" dense bars={monthBars} />
        </Section>

        <Section title="Night by night">
          <DataTable
            columns={NIGHT_COLUMNS}
            rows={rows}
            onRowPress={onRowPress}
            rowLabel={rowLabel}
          />
        </Section>
      </View>
      <View className="mt-12">
        <Hills />
      </View>
      <PeopleSheet visible={picking} onClose={closePicker} />
    </ScrollView>
  );
}

const NIGHT_COLUMNS = ['Night', 'In bed', 'Got up', 'Woke'];

/**
 * The sky with her state. The only part of Tonight that follows the pillow's heartbeat, so the
 * rest of the screen doesn't re-render every time the pillow checks in.
 */
const TonightSky = memo(function TonightSky({
  pillowId,
  residentId,
  name,
  night,
  events,
  live,
  contactId,
  tz,
  loading,
  onSwitchPerson,
}: {
  pillowId: string | null;
  residentId: string | null;
  name: string;
  night: NightWindow;
  events: EventRow[];
  /** The alert in progress: once someone is on it, the sky shows her as up, not alarmed. */
  live: IncidentRow | null;
  contactId: string | null;
  tz: string;
  loading: boolean;
  onSwitchPerson?: () => void;
}) {
  const row = usePillowState();
  const now = useNow();
  const photo = useResidentPhoto(residentId);
  const state = appState(row, events, now, live);
  const onIt = live?.acked_by && live.acked_by === contactId ? "You're on it." : 'Someone is on it.';
  const ping = usePillowCheck(pillowId, state === 'offline');
  const hour = ribbonNow(night, now);
  return (
    <SkyHeader
      state={state}
      name={name}
      initials={name.slice(0, 1)}
      photoUri={photo ?? undefined}
      nightProgress={hour === undefined ? undefined : hour / RIBBON_HOURS}
      detail={loading ? undefined : stateDetail(state, row, events, tz, now, ping, onIt)}
      onSwitchPerson={onSwitchPerson}
    />
  );
});

/** An alert in progress: what's happening, and the one thing to do about it. */
function AlertCard({
  pillowId,
  name,
  incident,
  tz,
  onTapped,
}: {
  pillowId: string;
  name: string;
  incident: IncidentRow;
  tz: string;
  /** "I'm on it" was tapped (this phone stops buzzing straight away), or it didn't go through (true, false). */
  onTapped: (tapped: boolean) => void;
}) {
  const { refresh } = usePillow();
  // Told the pillow: the button keeps spinning until the alert itself says someone is on it.
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const acked = incident.status === 'acknowledged';

  // The pillow only takes an ack while it is calling round; if the alert never changes, say so
  // rather than spin for good.
  useEffect(() => {
    if (!sent || acked) return;
    const wait = setTimeout(() => {
      setSent(false);
      onTapped(false);
      setError(`The pillow didn't confirm. Try again, or call ${name}.`);
    }, ACK_CONFIRM_MS);
    return () => clearTimeout(wait);
  }, [sent, acked, name, onTapped]);

  const ack = async () => {
    setError(null);
    onTapped(true);
    try {
      const me = await api<{ contact_id: string | null }>('/me');
      if (!me.contact_id) throw new Error(`This login isn't one of ${name}'s contacts yet.`);
      await api(`/pillows/${pillowId}/ack`, { method: 'POST', body: { contact_id: me.contact_id } });
      setSent(true);
      void refresh();
    } catch (e) {
      onTapped(false);
      setError(e instanceof Error ? e.message : `Couldn't tell the pillow. Try again, or call ${name}.`);
    }
  };

  return (
    <Card>
      <Text className="font-display text-xl text-ink">
        {acked ? (
          'Someone is on it'
        ) : (
          <>
            {name} <StatusWord state="alert">needs you</StatusWord>
          </>
        )}
      </Text>
      <Text className="font-sans text-base leading-6 text-ink-muted">
        {acked
          ? `Acknowledged at ${clockTime(incident.acked_at ?? incident.opened_at, tz)}. The pillow has told ${name} help is coming.`
          : `${name} didn't answer the pillow's check-in. Family were alerted at ${clockTime(incident.opened_at, tz)}.`}
      </Text>
      {error ? (
        <Text accessibilityLiveRegion="polite" className="font-sans text-sm text-danger-text">
          {error}
        </Text>
      ) : null}
      {acked ? null : <Button fullWidth variant="alert" title="I'm on it" loading={sent} onPress={ack} />}
    </Card>
  );
}

/** A titled part of the page. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <View className="gap-3">
      <Text accessibilityRole="header" className="font-display text-xl text-ink">
        {title}
      </Text>
      {children}
    </View>
  );
}

/** A trailing word: the italic serif in a state colour when it means something, plain muted otherwise. */
function Word({ word, state }: { word: string; state?: 'asleep' | 'up' }) {
  return state ? (
    <Text className="text-[15px]">
      <StatusWord state={state}>{word}</StatusWord>
    </Text>
  ) : (
    <Text className="font-sans text-[13px] text-ink-muted">{word}</Text>
  );
}

/** What kind of reminder it is, as an icon in the avatar's accent circle. */
function ReminderIcon({ kind }: { kind: ReminderToday['kind'] }) {
  const { colors } = useTheme();
  const Icon = kind === 'meds' ? PillIcon : kind === 'call' ? PhoneIcon : BellIcon;
  return (
    <View className="size-11 items-center justify-center rounded-full bg-accent/25">
      <Icon color={colors.ink} />
    </View>
  );
}

/**
 * The last four weeks at a glance: a thin column per night (sleep, orange cap on a flagged night), and
 * three numbers: average sleep, how often she gets up a night, and how many alerts there were.
 */
function monthOverview(
  events: Parameters<typeof weekSummaries>[0],
  incidents: Parameters<typeof weekSummaries>[1],
  night: Parameters<typeof weekSummaries>[2],
  tz: string,
  name: string,
) {
  const nights = weekSummaries(events, incidents, night, MONTH_NIGHTS, tz, name).reverse();
  const dayMonth = formatter('dayMonth', tz, { day: 'numeric', month: 'short' }, 'en-GB');
  let slept = 0;
  let sleptNights = 0;
  let trips = 0;
  let alerts = 0;
  const bars = nights.map((n, i) => {
    const minutes = sleptMinutes(events, n.window);
    if (minutes) {
      slept += minutes;
      sleptNights += 1;
    }
    trips += nightFacts(events, n.window, tz).trips;
    const flagged = isFlagged(n.tone);
    if (flagged) alerts += 1;
    const date = dayMonth.format(new Date(n.window.start));
    return {
      key: n.key,
      // A date under every seventh column, so the month reads as four weeks.
      label: (nights.length - 1 - i) % 7 === 0 ? date : '',
      name: `${shortDay(n.window, tz)} ${date}`,
      hours: minutes ? minutes / 60 : null,
      flagged,
    };
  });
  return {
    bars,
    averageSleep: sleptNights ? hm(slept / sleptNights) : '–',
    tripsPerNight: sleptNights ? (trips / sleptNights).toFixed(1) : '–',
    alerts: String(alerts),
  };
}
