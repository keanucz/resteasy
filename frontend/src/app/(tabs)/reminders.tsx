import { useLocalSearchParams } from 'expo-router';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, Text, View } from 'react-native';
import Animated, { useAnimatedRef, useScrollOffset } from 'react-native-reanimated';

import { BellHedgehog, bellHedgehogBox } from '@/components/BellHedgehog';
import { Button, IconButton } from '@/components/Button';
import { Toast, UndoToast } from '@/components/Feedback';
import { Hedgehog } from '@/components/Hedgehog';
import { List, ListRow } from '@/components/List';
import { ReminderForm, SpokenLine } from '@/components/ReminderForm';
import { SegmentedTabs } from '@/components/Selection';
import { ListRowSkeleton, SkeletonGroup, SummaryCardSkeleton } from '@/components/Skeleton';
import { SkyBackdrop } from '@/components/SkyHeader';
import { consentLine, MoveChoice, SlotSheet } from '@/components/SlotSheet';
import { BellIcon, ChevronIcon, PhoneIcon, PillIcon, PlusIcon } from '@/components/TabIcons';
import { type DragTarget, slotKey, WeekGrid, WeekKey } from '@/components/WeekGrid';
import { SKY_DETAIL } from '@/constants/sky';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useNow, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { UNDO_MS, useReminders } from '@/hooks/useReminders';
import { useTheme } from '@/hooks/useTheme';
import { deleteReminder, moveOneDay, type Reminder, updateReminder } from '@/services/reminders';
import {
  addDays,
  capitalise,
  clockIn,
  consentWords,
  dateIn,
  expandCalendar,
  formatClock,
  isPast,
  lowerDay,
  repeatWords,
  shiftDays,
  type Slot,
  thisDay,
  weekRange,
  weekStart,
  whenWords,
} from '@/services/schedule';

type Lens = 'list' | 'week';
const LENSES: readonly { value: Lens; label: string }[] = [
  { value: 'list', label: 'All reminders' },
  { value: 'week', label: 'Week' },
];

/** The header's sky: shorter than Tonight's, with the bell-ringing hedgehog on its hill. */
const HORIZON = 150;
const PERCH_SIZE = 72;
const PERCH_AT = 0.83;
/** How long "Saved" and the like float at the bottom. */
const NOTICE_MS = 3500;
/** How far ahead the "Next" card looks, in days from today. */
const NEXT_DAYS = 7;

const byTime = (a: Slot, b: Slot) => (a.date + a.time).localeCompare(b.date + b.time);

type Notice = { message: string; detail?: string };

/**
 * Reminders: what the pillow will say to her and when. First the next one, word for word, and the
 * button to add one; then every reminder (tap to change it), or the week to drag them around on.
 * Moving or skipping shows at once and is sent after a short Undo window. Opens on the grid with
 * `?view=week`, and on a new reminder with `?add=1`.
 */
export default function RemindersScreen() {
  const { pillowId } = usePillowLink();
  const pillow = usePillow();
  const now = useNow();
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';
  const name = pillow.resident?.preferred_name ?? 'Mum';
  const today = dateIn(now, tz);
  const nowTime = clockIn(now, tz);

  // Deep links: /reminders?view=week opens on the grid, ?add=1 straight into a new reminder.
  const params = useLocalSearchParams<{ view?: string; add?: string }>();
  const [view, setView] = useState<Lens>(params.view === 'week' ? 'week' : 'list');
  const [weekOffset, setWeekOffset] = useState(0);
  const monday = addDays(weekStart(today), weekOffset * 7);
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const nextEnd = addDays(today, NEXT_DAYS - 1);
  const start = monday < today ? monday : today;
  const end = addDays(monday, 6) > nextEnd ? addDays(monday, 6) : nextEnd;

  const data = useReminders(pillowId, start, end, tz, { date: today, occurrences: pillow.occurrences });
  const showSkeleton = useDelayedLoading(data.loading);
  const byId = useMemo(() => new Map(data.reminders.map((r) => [r.id, r])), [data.reminders]);

  const [slotOpen, setSlotOpen] = useState<Slot | null>(null);
  const [form, setForm] = useState<{ reminder: Reminder | null } | null>(
    params.add === '1' ? { reminder: null } : null,
  );
  const [choice, setChoice] = useState<{ slot: Slot; reminder: Reminder; date: string; time: string } | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [dragTarget, setDragTarget] = useState<DragTarget | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [ring, setRing] = useState(0);

  const scrollRef = useAnimatedRef<Animated.ScrollView>();
  const scrollY = useScrollOffset(scrollRef);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

  const upcoming = useMemo(
    () => data.slots.filter((s) => !isPast(s.date, s.time, today, nowTime)).sort(byTime),
    [data.slots, today, nowTime],
  );
  // The next one that will really play; one still waiting for her yes if none will.
  const next = upcoming.find((s) => s.consent === 'agreed') ?? upcoming.find((s) => s.consent === 'pending');

  /** A move, staged: shown now, sent when the Undo window closes. */
  const stageMove = useCallback(
    (message: string, preview: (slots: Slot[]) => Slot[], commit: () => Promise<unknown>) =>
      data.stage({ message, detail: `${name} will be asked again before it plays.`, preview, commit }),
    [data, name],
  );

  const onMove = useCallback(
    (slot: Slot, date: string, time: string) => {
      const reminder = byId.get(slot.reminder_id);
      if (!pillowId || !reminder) return;
      setSlotOpen(null);
      if (slot.recurring) {
        setPendingKey(slotKey(slot));
        setChoice({ slot, reminder, date, time });
        return;
      }
      stageMove(
        `Moved to ${lowerDay(whenWords(date, time, today))}`,
        (slots) =>
          slots
            .map((s) => (slotKey(s) === slotKey(slot) ? { ...s, date, time, consent: 'pending' as const } : s))
            .sort(byTime),
        () => updateReminder(pillowId, reminder.id, { on_date: date, time_of_day: time }),
      );
    },
    [byId, pillowId, stageMove, today],
  );

  const moveOnce = () => {
    if (!choice || !pillowId) return;
    const { slot, reminder, date, time } = choice;
    stageMove(
      `Moved to ${lowerDay(whenWords(date, time, today))}, just this once`,
      (slots) =>
        [
          ...slots.filter((s) => slotKey(s) !== slotKey(slot)),
          { ...slot, date, time, recurring: false, consent: 'pending' as const, status: null },
        ].sort(byTime),
      () => moveOneDay(pillowId, reminder, slot.date, date, time),
    );
    setChoice(null);
    setPendingKey(null);
  };

  const moveEvery = () => {
    if (!choice || !pillowId) return;
    const { slot, reminder, date, time } = choice;
    const moved = {
      ...reminder,
      time_of_day: time,
      days: shiftDays(reminder.days, slot.date, date),
      consent: 'pending' as const,
    };
    stageMove(
      `Now ${repeatWords(moved, today)} at ${formatClock(time)}`,
      (slots) =>
        [
          ...slots.filter((s) => s.reminder_id !== reminder.id || isPast(s.date, s.time, today, nowTime)),
          ...expandCalendar([moved], today, end, { date: today, status: new Map() }).filter(
            (s) => !isPast(s.date, s.time, today, nowTime),
          ),
        ].sort(byTime),
      () => updateReminder(pillowId, reminder.id, { time_of_day: time, days: moved.days }),
    );
    setChoice(null);
    setPendingKey(null);
  };

  const onSkip = useCallback(
    (slot: Slot) => {
      const reminder = byId.get(slot.reminder_id);
      if (!pillowId || !reminder) return;
      setSlotOpen(null);
      const day = thisDay(slot.date, today);
      data.stage({
        message: slot.recurring ? `Skipped ${day}` : 'Cancelled',
        detail: `${name} won't hear “${slot.label}” ${day.replace(/^this /, 'on ')}.`,
        preview: (slots) => slots.filter((s) => slotKey(s) !== slotKey(slot)),
        commit: () =>
          slot.recurring
            ? updateReminder(pillowId, reminder.id, { skip_dates: [...reminder.skip_dates, slot.date] })
            : deleteReminder(pillowId, reminder.id),
      });
    },
    [byId, pillowId, today, data, name],
  );

  const onDone = (message: string, detail?: string) => {
    setForm(null);
    setNotice({ message, detail });
    setRing((r) => r + 1);
    data.refresh();
    pillow.refresh();
  };

  const toast: ReactNode = dragTarget ? (
    <Toast
      message={`Moving to ${lowerDay(whenWords(dragTarget.date, dragTarget.time, today))}`}
      detail={dragTarget.past ? 'That time has already gone. Let go to put it back.' : `${name} will be asked again.`}
    />
  ) : data.staged ? (
    <UndoToast
      key={data.staged.message}
      message={data.staged.message}
      detail={data.staged.detail}
      duration={UNDO_MS}
      onUndo={data.undo}
    />
  ) : data.sendError ? (
    <Toast message={data.sendError} action={<Button variant="ghost" title="OK" onPress={data.clearSendError} />} />
  ) : notice ? (
    <Toast message={notice.message} detail={notice.detail} />
  ) : null;

  const empty = !data.loading && !data.error && data.reminders.length === 0;

  return (
    <View className="flex-1 bg-canvas">
      <Animated.ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerClassName="pb-28"
        scrollEnabled={dragTarget === null}
        refreshControl={<RefreshControl refreshing={false} onRefresh={data.refresh} />}
      >
        <Header name={name} ring={ring} resting={data.error !== null} />

        <View className="-mt-2 gap-8 px-4">
          {data.error ? (
            <ErrorCard text={data.error} onRetry={data.refresh} />
          ) : showSkeleton ? (
            <SkeletonGroup>
              <View className="gap-2.5">
                <SummaryCardSkeleton />
                <ListRowSkeleton />
                <ListRowSkeleton />
                <ListRowSkeleton />
              </View>
            </SkeletonGroup>
          ) : data.loading ? null : empty ? (
            <View className="gap-4">
              <EmptyCard name={name} />
              <AddButton name={name} onPress={() => setForm({ reminder: null })} />
            </View>
          ) : (
            <>
              <View className="gap-3">
                <NextCard
                  slot={next}
                  name={name}
                  today={today}
                  reminder={next ? byId.get(next.reminder_id) : undefined}
                />
                <AddButton name={name} onPress={() => setForm({ reminder: null })} />
              </View>

              <View className="gap-4">
                <SegmentedTabs options={LENSES} value={view} onChange={setView} />
                {view === 'list' ? (
                  <AllReminders
                    reminders={data.reminders}
                    name={name}
                    today={today}
                    onOpen={(r) => setForm({ reminder: r })}
                  />
                ) : (
                  <View className="gap-3">
                    <WeekNav
                      monday={monday}
                      current={weekOffset === 0}
                      onPrev={() => setWeekOffset(weekOffset - 1)}
                      onNext={() => setWeekOffset(weekOffset + 1)}
                      onToday={() => setWeekOffset(0)}
                    />
                    <WeekGrid
                      days={days}
                      today={today}
                      now={nowTime}
                      slots={data.slots}
                      name={name}
                      scrollRef={scrollRef}
                      scrollY={scrollY}
                      pendingKey={pendingKey}
                      onOpen={setSlotOpen}
                      onMove={onMove}
                      onSkip={onSkip}
                      onDragChange={setDragTarget}
                    />
                    <WeekKey days={days} slots={data.slots} name={name} />
                  </View>
                )}
              </View>
            </>
          )}
        </View>
      </Animated.ScrollView>

      <View pointerEvents="box-none" className="absolute bottom-3 left-4 right-4">
        {toast}
      </View>

      {pillowId ? (
        <ReminderForm
          visible={form !== null}
          pillowId={pillowId}
          name={name}
          today={today}
          now={nowTime}
          reminder={form?.reminder ?? null}
          onClose={() => setForm(null)}
          onDone={onDone}
        />
      ) : null}
      <SlotSheet
        slot={slotOpen}
        reminder={slotOpen ? byId.get(slotOpen.reminder_id) : undefined}
        name={name}
        today={today}
        now={nowTime}
        onClose={() => setSlotOpen(null)}
        onMove={onMove}
        onSkip={onSkip}
        onEdit={(r) => {
          setSlotOpen(null);
          setForm({ reminder: r });
        }}
      />
      <MoveChoice
        move={choice}
        name={name}
        today={today}
        onOnce={moveOnce}
        onEvery={moveEvery}
        onCancel={() => {
          setChoice(null);
          setPendingKey(null);
        }}
      />
    </View>
  );
}

/**
 * The top: a short night sky, the title, and the hedgehog with its bell on the hill. While the
 * reminders can't be reached it has put the bell down and dozes.
 */
function Header({ name, ring, resting }: { name: string; ring: number; resting: boolean }) {
  const { scheme } = useTheme();
  const perch = resting
    ? { width: PERCH_SIZE, height: (PERCH_SIZE * 38) / 56, node: <Hedgehog size={PERCH_SIZE} mood="asleep" /> }
    : { ...bellHedgehogBox(PERCH_SIZE), node: <BellHedgehog size={PERCH_SIZE} ring={ring} /> };
  return (
    <SkyBackdrop state="asleep" horizon={HORIZON} perch={{ at: PERCH_AT, ...perch }}>
      <View className="gap-2 px-[22px] pt-7">
        <Text accessibilityRole="header" className="font-display text-3xl text-ink">
          Reminders
        </Text>
        <Text className="w-3/4 font-sans text-sm" style={{ color: SKY_DETAIL[scheme] }}>
          What the pillow says to {name}, and when. Nothing plays until she agrees.
        </Text>
      </View>
    </SkyBackdrop>
  );
}

/** The next reminder that will play, word for word. */
function NextCard({
  slot,
  reminder,
  name,
  today,
}: {
  slot: Slot | undefined;
  reminder: Reminder | undefined;
  name: string;
  today: string;
}) {
  if (!slot) {
    return (
      <View className="gap-1 rounded-card bg-surface p-[18px]">
        <Text className="font-display text-xl text-ink">Nothing more this week</Text>
        <Text className="font-sans text-base text-ink-muted">The pillow has nothing to say to {name} for now.</Text>
      </View>
    );
  }
  const consent = consentLine(slot.consent, name);
  return (
    <View className="gap-3 rounded-card bg-surface p-[18px]">
      <SpokenLine
        name={name}
        label={slot.label}
        heading={`Next, ${lowerDay(whenWords(slot.date, slot.time, today))}`}
      />
      <Text className="font-sans text-sm text-ink-muted">
        {reminder ? capitalise(repeatWords(reminder, today)) : slot.recurring ? 'Repeats' : 'Just this once'}
        {slot.confirm ? `. ${name} is asked to say she's done it.` : '.'}
      </Text>
      {consent ? <Text className="font-sans text-sm text-ink">{consent}</Text> : null}
    </View>
  );
}

/** The one big way in: add a reminder. */
function AddButton({ name, onPress }: { name: string; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Add a reminder"
      accessibilityHint={`Set up something for the pillow to say to ${name}`}
      onPress={onPress}
      className="min-h-[60px] flex-row items-center gap-3.5 rounded-2xl bg-accent px-4 py-3 active:opacity-80"
    >
      <View className="size-9 items-center justify-center rounded-full bg-on-accent/15">
        <PlusIcon color={colors['on-accent']} size={20} />
      </View>
      <View className="flex-1">
        <Text className="font-sans-semibold text-[17px] text-on-accent">Add a reminder</Text>
        <Text className="font-sans text-sm text-on-accent">Tablets, water, a call, bedtime</Text>
      </View>
    </Pressable>
  );
}

/** The kind of reminder as an icon in a circle: filled once she agreed, a dashed ring while she hasn't. */
function KindIcon({ kind, consent, small = false }: { kind: Slot['kind']; consent: Slot['consent']; small?: boolean }) {
  const { colors } = useTheme();
  const Icon = kind === 'meds' ? PillIcon : kind === 'call' ? PhoneIcon : BellIcon;
  const look =
    consent === 'pending'
      ? 'border-[1.5px] border-dashed border-accent'
      : consent === 'declined'
        ? 'bg-hairline/60'
        : 'bg-accent/25';
  return (
    <View className={`${small ? 'size-8' : 'size-11'} items-center justify-center rounded-full ${look}`}>
      <Icon color={consent === 'declined' ? colors['ink-muted'] : colors.ink} size={small ? 16 : 20} />
    </View>
  );
}

/** Which week the grid shows, and the way to the ones either side. */
function WeekNav({
  monday,
  current,
  onPrev,
  onNext,
  onToday,
}: {
  monday: string;
  current: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View className="flex-row items-center gap-2">
      <IconButton label="Previous week" onPress={onPrev}>
        <ChevronIcon left color={colors.ink} />
      </IconButton>
      <View className="flex-1 items-center">
        <Text className="font-sans-semibold text-[15px] text-ink">{weekRange(monday)}</Text>
      </View>
      {current ? null : <Button variant="ghost" title="This week" onPress={onToday} />}
      <IconButton label="Next week" onPress={onNext}>
        <ChevronIcon color={colors.ink} />
      </IconButton>
    </View>
  );
}

/** Every reminder, to change or pause, with her consent in words on each that isn't yet a yes. */
function AllReminders({
  reminders,
  name,
  today,
  onOpen,
}: {
  reminders: Reminder[];
  name: string;
  today: string;
  onOpen: (r: Reminder) => void;
}) {
  const { colors } = useTheme();
  const sorted = [...reminders].sort((a, b) => a.time_of_day.localeCompare(b.time_of_day));
  return (
    <View className="gap-3">
      <List>
        {sorted.map((r) => {
          const consent = consentWords(r.consent, name);
          return (
            <ListRow
              key={r.id}
              leading={<KindIcon kind={r.kind} consent={r.consent} />}
              title={capitalise(r.label)}
              meta={
                r.active
                  ? `${capitalise(repeatWords(r, today))} at ${formatClock(r.time_of_day)}${consent ? `. ${consent}.` : ''}`
                  : "Paused. It won't play until you turn it back on."
              }
              trailing={<ChevronIcon color={colors['ink-muted']} size={18} />}
              onPress={() => onOpen(r)}
            />
          );
        })}
      </List>
      {/* The end of the list: a small hedgehog curled up in the gutter beside the hint, never behind a row. */}
      <View className="flex-row items-end gap-3 px-1">
        <Text className="flex-1 font-sans text-sm text-ink-muted">
          Tap one to change its words, time or days, or to pause it.
        </Text>
        <Hedgehog size={44} mood="asleep" />
      </View>
    </View>
  );
}

/** No reminders yet: a nudge towards a good first one (the hedgehog waits with its bell up top). */
function EmptyCard({ name }: { name: string }) {
  return (
    <View className="gap-1.5 rounded-card bg-surface p-[18px]">
      <Text className="font-display text-xl text-ink">Nothing to remind {name} about yet</Text>
      <Text className="font-sans text-base leading-6 text-ink-muted">
        {"Tablets are a good first one. The pillow says it out loud, once she's agreed."}
      </Text>
    </View>
  );
}

/** The reminders couldn't be read: say so plainly, and offer to try again. The rest of the app still works. */
function ErrorCard({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <View className="gap-3 rounded-card bg-surface p-[18px]">
      <View className="gap-1.5">
        <Text className="font-display text-xl text-ink">{"Reminders aren't here right now"}</Text>
        <Text className="font-sans text-base leading-6 text-ink-muted">{text}</Text>
      </View>
      <Button variant="secondary" title="Try again" onPress={onRetry} />
    </View>
  );
}
