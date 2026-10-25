import { memo, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as Haptics from 'expo-haptics';
import { Platform, Text, useWindowDimensions, View } from 'react-native';
import { GestureDetector, useCompetingGestures, usePanGesture, useTapGesture } from 'react-native-gesture-handler';
import Animated, {
  type AnimatedRef,
  measure,
  runOnJS,
  scrollTo,
  type SharedValue,
  useAnimatedRef,
  useAnimatedStyle,
  useFrameCallback,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { BellIcon, CheckIcon, PhoneIcon, PillIcon } from '@/components/TabIcons';
import { DURATION, EASE } from '@/constants/motion';
import { useTheme } from '@/hooks/useTheme';
import {
  capitalise,
  dayName,
  formatClock,
  isPast,
  minutesOf,
  type Slot,
  SNAP_MIN,
  thisDay,
  timeOf,
} from '@/services/schedule';

/** Width of the hour labels down the left, and the height of one hour. A quarter hour is 10 px. */
const RULER_W = 40;
const HOUR_H = 40;
/** A block is drawn about 45 minutes tall (a reminder is a moment, but needs room for a finger). */
const BLOCK_H = 34;
const BLOCK_MIN = (BLOCK_H / HOUR_H) * 60;
/**
 * The hours shown when nothing falls outside them: her waking day, 7 am to 10 pm (at night the
 * pillow holds a reminder until she is up anyway). Stretched to fit any reminder outside it.
 */
const FIRST_HOUR = 7;
const LAST_HOUR = 22;
/** Hold this long to pick a reminder up. */
const LIFT_MS = 400;
const LIFT_SCALE = 1.05;
/** At most two reminders side by side in a day; a third close in time sits this much lower. */
const MAX_LANES = 2;
const STACK_STEP = 12;
/** Near the top or bottom of the screen the page scrolls by itself, faster the closer the finger. */
const EDGE_TOP = 150;
const EDGE_BOTTOM = 190;
const EDGE_SPEED = 700;

/** Where a dragged reminder would land, in her days and times. */
export type DragTarget = { date: string; time: string; past: boolean };

type WeekGridProps = {
  /** Monday to Sunday, "YYYY-MM-DD". */
  days: string[];
  today: string;
  /** "HH:MM" now on her clock. */
  now: string;
  slots: Slot[];
  name: string;
  /** The page that scrolls, so a drag near an edge can carry on past it. */
  scrollRef: AnimatedRef<Animated.ScrollView>;
  scrollY: SharedValue<number>;
  /** A block's key awaiting "Only this day / Every time": it waits where it was dropped. */
  pendingKey: string | null;
  onOpen: (slot: Slot) => void;
  onMove: (slot: Slot, date: string, time: string) => void;
  /** Skip this day of it (or cancel a one-off): offered to screen readers as a direct action. */
  onSkip: (slot: Slot) => void;
  /** Where the dragged block would land as it moves, null when it is put down. */
  onDragChange: (target: DragTarget | null) => void;
};

/** A slot's identity on the grid: which reminder, which day, what time. */
export const slotKey = (s: Slot) => `${s.reminder_id}:${s.date}:${s.time}`;

/**
 * Side-by-side lanes for reminders close enough in time to overlap: [lane, lanes, row] per slot.
 * Two lanes at most, so a block stays wide enough for a finger; a third steps down a row.
 */
function lanes(daySlots: Slot[]): Map<string, [number, number, number]> {
  const placed = new Map<string, [number, number, number]>();
  const sorted = [...daySlots].sort((a, b) => a.time.localeCompare(b.time));
  let cluster: Slot[] = [];
  const flush = () => {
    const n = Math.min(cluster.length, MAX_LANES);
    cluster.forEach((s, i) => placed.set(slotKey(s), [i % n, n, Math.floor(i / n)]));
    cluster = [];
  };
  for (const s of sorted) {
    const last = cluster[cluster.length - 1];
    if (last && minutesOf(s.time) - minutesOf(last.time) >= BLOCK_MIN) flush();
    cluster.push(s);
  }
  flush();
  return placed;
}

/** A light touch on the phone for each moment of a drag (none on the web). Visual cues stay the main ones. */
function buzz(moment: 'lift' | 'snap' | 'drop') {
  if (Platform.OS === 'web') return;
  if (moment === 'lift') Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
  else if (moment === 'snap') Haptics.selectionAsync().catch(() => {});
  else Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
}

/** What a block says to a screen reader: the whole story in one sentence. */
function blockLabel(s: Slot, name: string, today: string, now: string): string {
  const when = `${dayName(s.date, true)} at ${formatClock(s.time)}`;
  const repeat = s.recurring ? ', repeats' : ', just this once';
  const consent =
    s.consent === 'pending' ? `, waiting for ${name} to agree` : s.consent === 'declined' ? `, ${name} said no` : '';
  const done = s.status === 'done' ? `, ${name} confirmed` : s.status === 'missed' ? ', not confirmed' : '';
  const past = isPast(s.date, s.time, today, now) ? ', already passed' : '';
  return `${capitalise(s.label)}, ${when}${repeat}${consent}${done}${past}`;
}

/**
 * The week as seven columns of her day, an hour per row, each reminder a small block at its time.
 * Hold a block to pick it up and drag it to another day or time: it snaps to quarter hours, a
 * ghost stays where it came from, and the page scrolls when it nears an edge. A tap opens it
 * instead, which is also how to move one without dragging. Past reminders stay put.
 */
export function WeekGrid({
  days,
  today,
  now,
  slots,
  name,
  scrollRef,
  scrollY,
  pendingKey,
  onOpen,
  onMove,
  onSkip,
  onDragChange,
}: WeekGridProps) {
  const { colors } = useTheme();
  const reduced = useReducedMotion();
  const { height: screenH } = useWindowDimensions();
  const [width, setWidth] = useState(0);
  const colW = width ? (width - RULER_W) / 7 : 0;

  // The visible hours: her waking day, stretched to fit anything earlier or later.
  const week = useMemo(() => slots.filter((s) => days.includes(s.date)), [slots, days]);
  const first = Math.min(FIRST_HOUR, ...week.map((s) => Math.floor(minutesOf(s.time) / 60)));
  const last = Math.min(24, Math.max(LAST_HOUR, ...week.map((s) => Math.ceil((minutesOf(s.time) + BLOCK_MIN) / 60))));
  const height = (last - first) * HOUR_H;
  const minMinute = first * 60;
  const maxMinute = last * 60 - SNAP_MIN;

  const placed = useMemo(() => {
    const all = new Map<string, [number, number, number]>();
    for (const d of days) lanes(week.filter((s) => s.date === d)).forEach((v, k) => all.set(k, v));
    return all;
  }, [week, days]);

  // One drag at a time: which block is up, where it started, and where it is now.
  const activeKey = useSharedValue('');
  const originDay = useSharedValue(0);
  const originMin = useSharedValue(0);
  // The finger on screen, and where on the block it took hold (from the column's middle, the block's top).
  const pointerX = useSharedValue(0);
  const pointerY = useSharedValue(0);
  const grabX = useSharedValue(0);
  const grabY = useSharedValue(0);
  const gridRef = useAnimatedRef<Animated.View>();
  const snapDay = useSharedValue(-1);
  const snapMin = useSharedValue(-1);
  const offsetX = useSharedValue(0);
  const offsetY = useSharedValue(0);
  const lift = useSharedValue(0);
  const edgeSpeed = useSharedValue(0);

  const report = useCallback(
    (day: number, minute: number) => {
      if (day < 0) return onDragChange(null);
      const date = days[day];
      const time = timeOf(minute);
      buzz('snap');
      onDragChange({ date, time, past: isPast(date, time, today, now) });
    },
    [days, today, now, onDragChange],
  );

  /**
   * Snap the dragged block to the quarter hour and day under the finger; tell the page when that
   * changes. Reads the grid's place on screen each time, so it stays right while the page scrolls.
   */
  const retarget = useCallback(() => {
    'worklet';
    const grid = measure(gridRef);
    if (!activeKey.get() || !colW || !grid) return;
    const x = pointerX.get() - grid.pageX - grabX.get() - RULER_W;
    const y = pointerY.get() - grid.pageY - grabY.get();
    const day = Math.max(0, Math.min(6, Math.round(x / colW)));
    const raw = minMinute + (y / HOUR_H) * 60;
    const minute = Math.max(minMinute, Math.min(maxMinute, Math.round(raw / SNAP_MIN) * SNAP_MIN));
    if (day === snapDay.get() && minute === snapMin.get()) return;
    snapDay.set(day);
    snapMin.set(minute);
    const dx = (day - originDay.get()) * colW;
    const dy = ((minute - originMin.get()) / 60) * HOUR_H;
    offsetX.set(reduced ? dx : withTiming(dx, { duration: DURATION.instant, easing: EASE.out }));
    offsetY.set(reduced ? dy : withTiming(dy, { duration: DURATION.instant, easing: EASE.out }));
    runOnJS(report)(day, minute);
  }, [
    gridRef,
    activeKey,
    colW,
    pointerX,
    pointerY,
    grabX,
    grabY,
    minMinute,
    maxMinute,
    snapDay,
    snapMin,
    originDay,
    originMin,
    offsetX,
    offsetY,
    reduced,
    report,
  ]);

  /** Where the finger took hold of a block, so the block keeps that spot under it. */
  const grab = useCallback(
    (day: number, minute: number, absoluteX: number, absoluteY: number) => {
      'worklet';
      const grid = measure(gridRef);
      if (!grid) return;
      grabX.set(absoluteX - grid.pageX - RULER_W - day * colW);
      grabY.set(absoluteY - grid.pageY - ((minute - minMinute) / 60) * HOUR_H);
    },
    [gridRef, grabX, grabY, colW, minMinute],
  );

  // Carry on scrolling while a dragged block is held near the top or bottom of the screen.
  useFrameCallback((frame) => {
    const speed = edgeSpeed.get();
    if (!activeKey.get() || speed === 0) return;
    const dt = (frame.timeSincePreviousFrame ?? 16) / 1000;
    const next = Math.max(0, scrollY.get() + speed * (reduced ? 0.5 : 1) * dt);
    scrollTo(scrollRef, 0, next, false);
    retarget();
  });

  /** Put the dragged block back where it came from (a drop on its own spot, the past, or Cancel). */
  const settle = useCallback(
    (animate: boolean) => {
      if (animate && !reduced) {
        offsetX.set(withTiming(0, { duration: DURATION.base, easing: EASE.out }));
        lift.set(withTiming(0, { duration: DURATION.base, easing: EASE.out }));
        offsetY.set(
          withTiming(0, { duration: DURATION.base, easing: EASE.out }, (done) => {
            'worklet';
            if (done) activeKey.set('');
          }),
        );
      } else {
        offsetX.set(0);
        offsetY.set(0);
        lift.set(0);
        activeKey.set('');
      }
    },
    [activeKey, lift, offsetX, offsetY, reduced],
  );

  const keys = useMemo(() => new Map(week.map((s) => [slotKey(s), s])), [week]);

  // A block waiting on "Only this day / Every time" goes back if the choice was Cancel, or simply
  // lets go once the change shows it in its new place.
  const waiting = useRef<string | null>(null);
  useEffect(() => {
    if (pendingKey) {
      waiting.current = pendingKey;
      return;
    }
    if (!waiting.current) return;
    settle(keys.has(waiting.current));
    waiting.current = null;
  }, [pendingKey, keys, settle]);

  const onDrop = useCallback(
    (key: string, day: number, minute: number) => {
      onDragChange(null);
      const slot = keys.get(key);
      if (!slot || day < 0) return settle(true);
      const date = days[day];
      const time = timeOf(minute);
      if ((date === slot.date && time === slot.time) || isPast(date, time, today, now)) return settle(true);
      buzz('drop');
      onMove(slot, date, time);
      // Not a recurring choice: the move shows at once, so this block can let go.
      if (!slot.recurring) settle(false);
    },
    [keys, days, today, now, onMove, onDragChange, settle],
  );

  const hours = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const nowMinute = minutesOf(now);
  const todayIndex = days.indexOf(today);

  return (
    <View>
      <View className="flex-row pb-2" importantForAccessibility="no-hide-descendants">
        <View style={{ width: RULER_W }} />
        {days.map((d) => {
          const isToday = d === today;
          return (
            <View key={d} className="flex-1 items-center gap-0.5">
              <Text className={`font-sans text-xs ${isToday ? 'text-ink' : 'text-ink-muted'}`}>{dayName(d)}</Text>
              <Text className={`text-base ${isToday ? 'font-sans-bold text-ink' : 'font-sans text-ink-muted'}`}>
                {Number(d.slice(8, 10))}
              </Text>
              {/* Today is marked by weight and a short rule under its date, not another colour. */}
              <View className={`h-0.5 w-4 rounded-full ${isToday ? 'bg-ink' : ''}`} />
            </View>
          );
        })}
      </View>

      <Animated.View ref={gridRef} style={{ height }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {hours.map((h) => {
          // Every other hour from 8 am is named (8 am, 10 am, noon...), so any block can be placed at a glance.
          const named = h >= 8 && h < 24 && (h - 8) % 2 === 0;
          return (
            <View
              key={h}
              pointerEvents="none"
              className="absolute left-0 right-0 flex-row items-center"
              style={{ top: (h - first) * HOUR_H - 8, height: 16 }}
            >
              <Text style={{ width: RULER_W - 6 }} className="text-right font-sans text-[11px] text-ink-muted">
                {named ? hourLabel(h) : ''}
              </Text>
              <View className="ml-1.5 h-px flex-1 bg-hairline" style={{ opacity: named ? 1 : 0.5 }} />
            </View>
          );
        })}
        {colW
          ? days.map((d, i) => (
              <View
                key={d}
                pointerEvents="none"
                className="absolute top-0 border-l border-hairline/60"
                style={{ left: RULER_W + i * colW, width: colW, height }}
              />
            ))
          : null}

        {/* Now, as a line across today's column. */}
        {colW && todayIndex >= 0 && nowMinute >= minMinute && nowMinute <= last * 60 ? (
          <View
            pointerEvents="none"
            className="absolute flex-row items-center"
            style={{
              left: RULER_W + todayIndex * colW - 3,
              width: colW + 3,
              top: ((nowMinute - minMinute) / 60) * HOUR_H - 3,
            }}
          >
            <View className="size-1.5 rounded-full bg-ink" />
            <View className="h-0.5 flex-1 bg-ink" />
          </View>
        ) : null}

        {colW
          ? week.map((s) => {
              const key = slotKey(s);
              const [lane, n, row] = placed.get(key) ?? [0, 1, 0];
              const day = days.indexOf(s.date);
              const laneW = colW / n;
              return (
                <Block
                  key={key}
                  slotKey={key}
                  slot={s}
                  day={day}
                  left={RULER_W + day * colW + lane * laneW + 2}
                  top={((minutesOf(s.time) - minMinute) / 60) * HOUR_H + row * STACK_STEP}
                  width={laneW - 4}
                  past={isPast(s.date, s.time, today, now)}
                  label={blockLabel(s, name, today, now)}
                  skipLabel={s.recurring ? `Skip ${thisDay(s.date, today)}` : 'Cancel this one'}
                  colors={colors}
                  drag={{ activeKey, originDay, originMin, pointerX, pointerY, snapDay, snapMin }}
                  grab={grab}
                  offsetX={offsetX}
                  offsetY={offsetY}
                  lift={lift}
                  edgeSpeed={edgeSpeed}
                  screenH={screenH}
                  reduced={reduced}
                  retarget={retarget}
                  onDrop={onDrop}
                  onOpen={onOpen}
                  onSkip={onSkip}
                />
              );
            })
          : null}
      </Animated.View>
    </View>
  );
}

/** "#9499E6" at `opacity`, as an 8-digit hex colour. */
const alpha = (hex: string, opacity: number) =>
  `${hex}${Math.round(opacity * 255)
    .toString(16)
    .padStart(2, '0')}`;

type Colors = ReturnType<typeof useTheme>['colors'];

/**
 * A block's fill for her consent: agreed is filled, waiting for her a dashed outline, a no faint.
 * `faded` (gone by, nothing to report) softens only the fill, so its icon and time stay readable.
 * Reanimated views take styles, not class names, so the theme's colours are applied directly.
 */
function blockFill(consent: Slot['consent'], colors: Colors, faded = false) {
  if (consent === 'pending') {
    return {
      borderWidth: 1.5,
      borderStyle: 'dashed' as const,
      borderColor: faded ? alpha(colors.accent, 0.5) : colors.accent,
      backgroundColor: colors.canvas,
    };
  }
  const tint =
    consent === 'declined' ? alpha(colors.hairline, faded ? 0.3 : 0.5) : alpha(colors.accent, faded ? 0.14 : 0.3);
  return { backgroundColor: tint };
}

/** "6 am", "noon", "9 pm". */
function hourLabel(h: number): string {
  if (h === 12) return 'noon';
  return `${h % 12 || 12} ${h < 12 ? 'am' : 'pm'}`;
}

type DragValues = {
  activeKey: SharedValue<string>;
  originDay: SharedValue<number>;
  originMin: SharedValue<number>;
  pointerX: SharedValue<number>;
  pointerY: SharedValue<number>;
  snapDay: SharedValue<number>;
  snapMin: SharedValue<number>;
};

type BlockProps = {
  slotKey: string;
  slot: Slot;
  day: number;
  left: number;
  top: number;
  width: number;
  past: boolean;
  label: string;
  /** "Skip tomorrow" or "Cancel this one", for screen readers. */
  skipLabel: string;
  colors: Colors;
  drag: DragValues;
  offsetX: SharedValue<number>;
  offsetY: SharedValue<number>;
  lift: SharedValue<number>;
  edgeSpeed: SharedValue<number>;
  screenH: number;
  reduced: boolean;
  retarget: () => void;
  grab: (day: number, minute: number, absoluteX: number, absoluteY: number) => void;
  onDrop: (key: string, day: number, minute: number) => void;
  onOpen: (slot: Slot) => void;
  onSkip: (slot: Slot) => void;
};

/**
 * One reminder on the grid: its kind as an icon and its time. Agreed reminders are filled;
 * waiting for her a dashed outline; ones she said no to faint. Done shows a tick, not confirmed a
 * warm time, the only warm thing on the grid.
 */
const Block = memo(function Block({
  slotKey: key,
  slot,
  day,
  left,
  top,
  width,
  past,
  label,
  skipLabel,
  colors,
  drag,
  offsetX,
  offsetY,
  lift,
  edgeSpeed,
  screenH,
  reduced,
  retarget,
  grab,
  onDrop,
  onOpen,
  onSkip,
}: BlockProps) {
  const movable = !past;
  const minute = minutesOf(slot.time);
  const open = useCallback(() => onOpen(slot), [onOpen, slot]);
  const act = useCallback(
    (e: { nativeEvent: { actionName: string } }) => (e.nativeEvent.actionName === 'skip' ? onSkip(slot) : onOpen(slot)),
    [onOpen, onSkip, slot],
  );

  const pan = usePanGesture({
    enabled: movable,
    activateAfterLongPress: LIFT_MS,
    onActivate: (e) => {
      'worklet';
      drag.activeKey.set(key);
      drag.originDay.set(day);
      drag.originMin.set(minute);
      drag.pointerX.set(e.absoluteX);
      drag.pointerY.set(e.absoluteY);
      grab(day, minute, e.absoluteX, e.absoluteY);
      drag.snapDay.set(day);
      drag.snapMin.set(minute);
      offsetX.set(0);
      offsetY.set(0);
      lift.set(reduced ? 1 : withTiming(1, { duration: DURATION.fast, easing: EASE.out }));
      runOnJS(buzz)('lift');
    },
    onUpdate: (e) => {
      'worklet';
      if (drag.activeKey.get() !== key) return;
      drag.pointerX.set(e.absoluteX);
      drag.pointerY.set(e.absoluteY);
      const y = e.absoluteY;
      edgeSpeed.set(
        y < EDGE_TOP
          ? -EDGE_SPEED * (1 - y / EDGE_TOP)
          : y > screenH - EDGE_BOTTOM
            ? EDGE_SPEED * Math.min(1, (y - (screenH - EDGE_BOTTOM)) / EDGE_BOTTOM)
            : 0,
      );
      retarget();
    },
    onDeactivate: (e) => {
      'worklet';
      edgeSpeed.set(0);
      if (drag.activeKey.get() !== key) return;
      runOnJS(onDrop)(key, e.canceled ? -1 : drag.snapDay.get(), drag.snapMin.get());
    },
  });
  const tap = useTapGesture({
    onActivate: () => {
      'worklet';
      runOnJS(open)();
    },
  });
  const gesture = useCompetingGestures(pan, tap);

  // The ghost left where the block was picked up from.
  const ghost = useAnimatedStyle(() => ({ opacity: drag.activeKey.get() === key ? 1 : 0 }));

  const style = useAnimatedStyle(() => {
    const me = drag.activeKey.get() === key;
    const l = me ? lift.get() : 0;
    return {
      zIndex: me ? 20 : 1,
      shadowOpacity: l * 0.35,
      elevation: l * 8,
      transform: [
        { translateX: me ? offsetX.get() : 0 },
        { translateY: me ? offsetY.get() : 0 },
        { scale: 1 + (LIFT_SCALE - 1) * l },
      ],
    };
  });

  const declined = slot.consent === 'declined';
  const missed = slot.status === 'missed';
  const done = slot.status === 'done' || slot.status === 'announced';
  const Icon = done ? CheckIcon : slot.kind === 'meds' ? PillIcon : slot.kind === 'call' ? PhoneIcon : BellIcon;
  const iconColor = done ? colors['state-asleep'] : declined ? colors['ink-muted'] : colors.ink;
  const [h, m] = slot.time.split(':').map(Number);
  const short = `${h % 12 || 12}${m ? `:${String(m).padStart(2, '0')}` : ''}`;

  const fill = blockFill(slot.consent, colors, past && !missed && !done);

  return (
    <>
      <Animated.View
        pointerEvents="none"
        style={[
          {
            position: 'absolute',
            left,
            top,
            width,
            height: BLOCK_H,
            borderRadius: 8,
            borderWidth: 1,
            borderStyle: 'dashed',
            borderColor: colors['ink-muted'],
          },
          ghost,
        ]}
      />
      <GestureDetector gesture={gesture}>
        <Animated.View
          accessible
          accessibilityRole="button"
          accessibilityLabel={label}
          accessibilityHint={movable ? 'Opens it, to change the day or time' : 'Opens it'}
          accessibilityActions={
            movable
              ? [
                  { name: 'activate' },
                  { name: 'move', label: 'Change day or time' },
                  { name: 'skip', label: skipLabel },
                ]
              : [{ name: 'activate' }]
          }
          onAccessibilityAction={act}
          style={[
            {
              position: 'absolute',
              left,
              top,
              width,
              height: BLOCK_H,
              borderRadius: 8,
              alignItems: 'center',
              justifyContent: 'center',
              shadowColor: '#000',
              shadowRadius: 10,
              shadowOffset: { width: 0, height: 4 },
            },
            fill,
            style,
          ]}
          hitSlop={{ top: 5, bottom: 5 }}
        >
          <Icon color={iconColor} size={width < 30 ? 12 : 14} />
          {width >= 30 ? (
            <Text
              numberOfLines={1}
              className={`font-sans-semibold text-[11px] ${missed ? 'text-state-up' : declined ? 'text-ink-muted' : 'text-ink'}`}
            >
              {short}
            </Text>
          ) : null}
        </Animated.View>
      </GestureDetector>
    </>
  );
});

/**
 * How to use the grid, then what each look of a block means, in words beside a small copy of it.
 * Only the looks this week has are listed, so the key stays short.
 */
export function WeekKey({ days, slots, name }: { days: string[]; slots: Slot[]; name: string }) {
  const { colors } = useTheme();
  const week = slots.filter((s) => days.includes(s.date));
  const has = (test: (s: Slot) => boolean) => week.some(test);
  const sample = (consent: Slot['consent'], inner?: ReactNode) => (
    <View
      style={[
        { width: 30, height: 22, borderRadius: 6, alignItems: 'center', justifyContent: 'center' },
        blockFill(consent, colors),
      ]}
    >
      {inner}
    </View>
  );
  const lines: { key: string; look: ReactNode; text: string }[] = [];
  if (has((s) => s.consent === 'pending')) {
    lines.push({
      key: 'pending',
      look: sample('pending'),
      text: `Waiting for ${name} to agree. It won't play until she does.`,
    });
  }
  if (has((s) => s.consent === 'declined')) {
    lines.push({
      key: 'declined',
      look: sample('declined', <BellIcon color={colors['ink-muted']} size={12} />),
      text: `${name} said no, so it won't play.`,
    });
  }
  if (has((s) => s.status === 'done' || s.status === 'announced')) {
    lines.push({
      key: 'played',
      look: sample('agreed', <CheckIcon color={colors['state-asleep']} size={12} />),
      text: 'It played.',
    });
  }
  if (has((s) => s.status === 'missed')) {
    lines.push({
      key: 'missed',
      look: sample('agreed', <Text className="font-sans-semibold text-[11px] text-state-up">8</Text>),
      text: `Not confirmed: ${name} didn't say she'd done it.`,
    });
  }
  return (
    <View className="gap-2.5">
      <Text className="font-sans text-sm text-ink-muted">
        Hold a reminder to drag it to another day or time, or tap it to change it.
      </Text>
      {lines.map((l) => (
        <View key={l.key} className="flex-row items-center gap-3">
          {l.look}
          <Text className="flex-1 font-sans text-sm text-ink">{l.text}</Text>
        </View>
      ))}
    </View>
  );
}
