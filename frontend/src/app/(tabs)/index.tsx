import { router } from 'expo-router';
import { type ReactNode, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import {
  hm,
  MovementChart,
  nightShare,
  nightWindow,
  TemperatureChart,
  type WeekBar,
  WeekSleepChart,
} from '@/components/Charts';
import { List, ListRow } from '@/components/List';
import { NightHeading } from '@/components/NightHeading';
import { NightRibbon } from '@/components/NightRibbon';
import { PeopleSheet } from '@/components/PeoplePicker';
import { SkeletonGroup, StatTileSkeleton, SummaryCardSkeleton } from '@/components/Skeleton';
import { SkyHeader } from '@/components/SkyHeader';
import { DataTable, StatTile, SummaryCard } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { BellIcon, PhoneIcon, PillIcon } from '@/components/TabIcons';
import { MONTH_NIGHTS, RIBBON_HOURS, WEEK_NIGHTS } from '@/constants/pillow';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useNow, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useReadings } from '@/hooks/useReadings';
import { useResidentPhoto } from '@/hooks/useResidentPhoto';
import { useTheme } from '@/hooks/useTheme';
import { api } from '@/services/api';
import {
  appState,
  clockTime,
  type IncidentRow,
  latestNight,
  nightFacts,
  nightStats,
  ribbonNow,
  ribbonSegments,
  type ReminderToday,
  shortDay,
  stateDetail,
  summariseNight,
  todaysReminders,
  weekSummaries,
} from '@/services/night';
import { nightClimate, signedDegrees } from '@/services/readings';

/** What happened to today's reminder: a word, coloured only when it went well or needs a look. */
const REMINDER_WORD: Record<ReminderToday['status'], { word: string; state?: 'asleep' | 'up' }> = {
  later: { word: 'Later' },
  waiting: { word: 'Waiting' },
  due: { word: 'Reminding' },
  announced: { word: 'Reminded' },
  done: { word: 'Done', state: 'asleep' },
  missed: { word: 'Not confirmed', state: 'up' },
};

/**
 * Tonight: the sky says how she is (and the hedgehog walks the arch while she sleeps), the summary
 * and charts say how the night is going, then anything that needs you, today's reminders and the
 * week. Tap a night in the week to open it.
 */
export default function TonightScreen() {
  const { pillowId, people } = usePillowLink();
  const pillow = usePillow();
  const [picking, setPicking] = useState(false);
  const now = useNow();
  const showSkeleton = useDelayedLoading(pillow.loading);
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';
  const name = pillow.resident?.preferred_name ?? 'Mum';
  const photo = useResidentPhoto(pillow.resident?.id ?? null);

  const night = latestNight(pillow.events, now, tz);
  const window = useMemo(() => nightWindow(night.ribbonStart), [night.ribbonStart]);
  const readings = useReadings(pillowId, window.start - 60 * 60 * 1000, window.end, !night.over);
  const climate = nightClimate(readings.rows);

  const state = appState(pillow.state, pillow.events, now);
  const stats = nightStats(pillow.events, night, now);
  const segments = ribbonSegments(pillow.events, night, now);
  const summary = summariseNight(pillow.events, pillow.incidents, night, night.over ? 'Last night' : 'Tonight', name);
  const week = weekSummaries(pillow.events, pillow.incidents, night, WEEK_NIGHTS, tz, name);
  const reminders = todaysReminders(pillow.reminders, pillow.occurrences, now, tz);
  const live = pillow.incidents.find((i) => i.status === 'open' || i.status === 'acknowledged');
  const hour = ribbonNow(night, now);

  const open = (start: number) => router.push({ pathname: '/night/[start]', params: { start: String(start) } });
  const oldestFirst = [...week].reverse();
  const bars: WeekBar[] = oldestFirst.map((n) => {
    const share = nightShare(ribbonSegments(pillow.events, n.window, n.window.end));
    const minutes = share.asleep + share.restless;
    return {
      key: n.key,
      label: shortDay(n.window, tz),
      hours: minutes ? minutes / 60 : null,
      flagged: n.tone === 'alerted' || n.tone === 'cold' || n.tone === 'hot',
      onPress: () => open(n.key),
    };
  });
  const facts = week.map((n) => nightFacts(pillow.events, n.window, tz));
  const month = useMemo(
    () => monthOverview(pillow.events, pillow.incidents, night, tz, name),
    // `night` changes identity every tick; its start is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pillow.events, pillow.incidents, night.start, night.over, tz, name],
  );

  return (
    <ScrollView
      className="flex-1 bg-canvas"
      contentContainerClassName="pb-12"
      refreshControl={<RefreshControl refreshing={false} onRefresh={pillow.refresh} />}
    >
      <SkyHeader
        state={state}
        name={name}
        initials={name.slice(0, 1)}
        photoUri={photo ?? undefined}
        nightProgress={hour === undefined ? undefined : hour / RIBBON_HOURS}
        detail={pillow.loading ? undefined : stateDetail(state, pillow.state, pillow.events, tz, now)}
        onSwitchPerson={people.length > 1 ? () => setPicking(true) : undefined}
      />
      <View className="-mt-2 gap-8 px-4">
        {pillow.error ? <Text className="font-sans text-sm text-danger-text">{pillow.error}</Text> : null}
        {live && pillowId ? <AlertCard pillowId={pillowId} name={name} incident={live} tz={tz} /> : null}

        {showSkeleton ? (
          <SkeletonGroup>
            <View className="gap-2.5">
              <SummaryCardSkeleton />
              <View className="flex-row gap-2.5">
                <StatTileSkeleton />
                <StatTileSkeleton />
                <StatTileSkeleton />
              </View>
            </View>
          </SkeletonGroup>
        ) : (
          <View className="gap-2.5">
            <SummaryCard heading={<NightHeading tone={summary.tone} soFar={!night.over} />} body={summary.line} />
            <Card>
              <NightRibbon segments={segments} now={hour} />
            </Card>
            <View className="flex-row gap-2.5">
              <StatTile label={stats.asleepLabel} value={stats.asleepValue} />
              <StatTile label="Out of bed" value={stats.tripsValue} />
              <StatTile
                label="Bedroom"
                value={climate ? `${climate.end.toFixed(1)}°C` : '–'}
                detail={climate ? `${signedDegrees(climate.end - climate.start)} since bed` : undefined}
              />
            </View>
            <TemperatureChart rows={readings.rows} window={window} tz={tz} />
            <MovementChart rows={readings.rows} window={window} tz={tz} />
          </View>
        )}

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

        <Section title="Past four weeks">
          <View className="flex-row gap-2.5">
            <StatTile label="Average sleep" value={month.averageSleep} />
            <StatTile label="Up a night" value={month.tripsPerNight} />
            <StatTile label="Alerts" value={month.alerts} />
          </View>
          <WeekSleepChart
            title="Sleep, last 28 nights"
            dense
            bars={month.bars.map((b) => ({ ...b, onPress: () => open(b.key) }))}
          />
        </Section>

        <Section title={night.over ? 'Earlier this week' : 'This week'}>
          <WeekSleepChart bars={bars} />
          <DataTable
            columns={['Night', 'In bed', 'Got up', 'Woke']}
            rows={week.map((n, i) => [
              shortDay(n.window, tz),
              facts[i].inBed ?? '–',
              facts[i].trips ? (
                <Text key="up" className="text-sm">
                  <StatusWord state="up">{facts[i].tripsWord}</StatusWord>
                </Text>
              ) : (
                <Text key="no" className="font-sans text-sm text-ink-muted">
                  {facts[i].inBed ? 'No' : '–'}
                </Text>
              ),
              facts[i].woke ?? '–',
            ])}
            onRowPress={(i) => open(week[i].key)}
            rowLabel={(i) => `${week[i].title}: ${week[i].line} Open the night.`}
          />
        </Section>
      </View>
      <PeopleSheet visible={picking} onClose={() => setPicking(false)} />
    </ScrollView>
  );
}

/** An alert in progress: what's happening, and the one thing to do about it. */
function AlertCard({
  pillowId,
  name,
  incident,
  tz,
}: {
  pillowId: string;
  name: string;
  incident: IncidentRow;
  tz: string;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const acked = incident.status === 'acknowledged';

  const ack = async () => {
    setPending(true);
    setError(null);
    try {
      const me = await api<{ contact_id: string | null }>('/me');
      if (!me.contact_id) throw new Error(`This login isn't one of ${name}'s contacts yet.`);
      await api(`/pillows/${pillowId}/ack`, { method: 'POST', body: { contact_id: me.contact_id } });
    } catch (e) {
      setError(e instanceof Error ? e.message : `Couldn't tell the pillow. Try again, or call ${name}.`);
    } finally {
      setPending(false);
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
      {error ? <Text className="font-sans text-sm text-danger-text">{error}</Text> : null}
      {acked ? null : <Button fullWidth variant="alert" title="I'm on it" loading={pending} onPress={ack} />}
    </Card>
  );
}

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
 * The last four weeks at a glance: a thin column per night (sleep, amber cap on an alert night), and
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
  const dayMonth = new Intl.DateTimeFormat('en-GB', { timeZone: tz, day: 'numeric', month: 'short' });
  let slept = 0;
  let sleptNights = 0;
  let trips = 0;
  let alerts = 0;
  const bars = nights.map((n, i) => {
    const share = nightShare(ribbonSegments(events, n.window, n.window.end));
    const minutes = share.asleep + share.restless;
    if (minutes) {
      slept += minutes;
      sleptNights += 1;
    }
    trips += nightFacts(events, n.window, tz).trips;
    const flagged = n.tone === 'alerted' || n.tone === 'cold' || n.tone === 'hot';
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
