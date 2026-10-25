import { router } from 'expo-router';
import { type ReactNode, useMemo, useState } from 'react';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { hm, type WeekBar, WeekSleepChart } from '@/components/Charts';
import { Hills } from '@/components/Hills';
import { List, ListRow } from '@/components/List';
import { NightDetail } from '@/components/NightDetail';
import { PeopleSheet } from '@/components/PeoplePicker';
import { SkyHeader } from '@/components/SkyHeader';
import { DataTable, StatTile } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { BellIcon, PhoneIcon, PillIcon } from '@/components/TabIcons';
import { MONTH_NIGHTS, RIBBON_HOURS, WEEK_NIGHTS } from '@/constants/pillow';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useNow, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useResidentPhoto } from '@/hooks/useResidentPhoto';
import { useTheme } from '@/hooks/useTheme';
import { api } from '@/services/api';
import {
  appState,
  clockTime,
  type IncidentRow,
  isFlagged,
  latestNight,
  nightFacts,
  nightTitle,
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

/**
 * Tonight: the sky says how she is (and the hedgehog keeps her company on the arch), then anything
 * that needs you and today's reminders, then the latest night in full, the week and the month as
 * sleep charts, and the nights one by one. Tap a night in a chart or the list to open it.
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
  const title = nightTitle(night, now, tz);
  const state = appState(pillow.state, pillow.events, now);
  const week = weekSummaries(pillow.events, pillow.incidents, night, WEEK_NIGHTS, tz, name);
  const reminders = todaysReminders(pillow.reminders, pillow.occurrences, now, tz);
  const live = pillow.incidents.find((i) => i.status === 'open' || i.status === 'acknowledged');
  const hour = ribbonNow(night, now);

  const open = (start: number) => router.push({ pathname: '/night/[start]', params: { start: String(start) } });
  const bars: WeekBar[] = [...week].reverse().map((n) => {
    const minutes = sleptMinutes(pillow.events, n.window);
    return {
      key: n.key,
      label: shortDay(n.window, tz),
      hours: minutes ? minutes / 60 : null,
      flagged: isFlagged(n.tone),
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
          <WeekSleepChart
            title="Sleep, last 28 nights"
            dense
            bars={month.bars.map((b) => ({ ...b, onPress: () => open(b.key) }))}
          />
        </Section>

        <Section title="Night by night">
          <DataTable
            columns={['Night', 'In bed', 'Got up', 'Woke']}
            rows={week.map((n, i) => [
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
            ])}
            onRowPress={(i) => open(week[i].key)}
            rowLabel={(i) => `${week[i].title}: ${week[i].line} Open the night.`}
          />
        </Section>
      </View>
      <View className="mt-12">
        <Hills />
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
  const dayMonth = new Intl.DateTimeFormat('en-GB', { timeZone: tz, day: 'numeric', month: 'short' });
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
