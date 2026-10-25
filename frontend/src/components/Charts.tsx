import { scaleLinear } from 'd3-scale';
import { arc, area, curveMonotoneX, line, pie } from 'd3-shape';
import { type ReactNode, useCallback, useMemo, useState } from 'react';
import { type GestureResponderEvent, Pressable, Text, useWindowDimensions, View } from 'react-native';
import Svg, { Circle, G, Line, Path, Rect } from 'react-native-svg';

import type { RibbonSegment } from '@/components/NightRibbon';
import { useTheme } from '@/hooks/useTheme';
import { bucket, onPillowSpans, type Point, type Reading } from '@/services/readings';

/**
 * Night charts in the style guide's quiet register: 2px lines, 10% washes, hairline guides, no
 * legends for a single series, direct labels on the one value that matters. Every chart spans the
 * ribbon's night (10 pm to 7 am) so they line up under it, and scrubbing reads a value out.
 */

const HOUR_MS = 60 * 60 * 1000;
const NIGHT_HOURS = 9;
/** Comfortable bedroom for sleep, the band shaded on the temperature chart. */
const COMFORT_C: [number, number] = [16, 20];
const TEMP_BUCKET_MIN = 10;
const MOTION_BUCKET_MIN = 5;
const PAD = { top: 10, bottom: 6, left: 0, right: 0 };
/** Room on the temperature chart's right for its degree labels, so the line never runs under them. */
const TEMP_AXIS = 30;
/** The page gutter and the card's padding on each side: a plot's width before it is measured. */
const CHART_INSET = 16 + 18;

export type ChartWindow = { start: number; end: number };

/** The ribbon's night: 10 pm to 7 am from `ribbonStart`. */
export const nightWindow = (ribbonStart: number): ChartWindow => ({
  start: ribbonStart,
  end: ribbonStart + NIGHT_HOURS * HOUR_MS,
});

/**
 * The plot's width: a guess from the screen first, so the chart draws on the first frame, then the
 * measured width once layout reports it.
 */
function useWidth() {
  const screen = useWindowDimensions().width;
  const [width, setWidth] = useState(() => Math.max(0, Math.round(screen - CHART_INSET * 2)));
  const onLayout = useCallback((e: { nativeEvent: { layout: { width: number } } }) => {
    const next = Math.round(e.nativeEvent.layout.width);
    setWidth((w) => (w === next ? w : next));
  }, []);
  return { width, onLayout };
}

const clock = (t: number, tz: string) =>
  new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' })
    .format(new Date(t))
    .replace(' AM', ' am')
    .replace(' PM', ' pm');

/** 10 pm, 1 am, 4 am, 7 am: three-hour steps, so they space evenly. */
function HourAxis({ inset = 0 }: { inset?: number }) {
  return (
    <View className="mt-1.5 flex-row justify-between" style={{ paddingRight: inset }}>
      {['10 pm', '1 am', '4 am', '7 am'].map((h) => (
        <Text key={h} className="font-sans text-xs text-ink-muted">
          {h}
        </Text>
      ))}
    </View>
  );
}

type FrameProps = {
  title: string;
  /** What the chart shows right now, or at the scrubbed time. Kept to one line so nothing moves. */
  readout: string;
  summary: string;
  /** Room kept free on the plot's right (for value labels), so the hours line up with the plot. */
  axisInset?: number;
  children: ReactNode;
};

/** Card with a title, a one-line live readout and the hour axis under the plot. */
function ChartCard({ title, readout, summary, axisInset, children }: FrameProps) {
  return (
    <View className="gap-1 rounded-card bg-surface p-[18px]" accessible accessibilityLabel={`${title}. ${summary}`}>
      <View className="flex-row items-baseline justify-between gap-3">
        <Text className="font-display text-lg text-ink">{title}</Text>
        <Text numberOfLines={1} className="shrink font-sans text-sm text-ink-muted">
          {readout}
        </Text>
      </View>
      {children}
      <HourAxis inset={axisInset} />
    </View>
  );
}

/** Touch, drag or hover over a plot to read a time out of it; lets go when the finger lifts. */
function useScrub(width: number, window: ChartWindow) {
  const [at, setAt] = useState<number | null>(null);
  const toTime = useCallback(
    (x: number) => window.start + Math.min(Math.max(x / Math.max(width, 1), 0), 1) * (window.end - window.start),
    [width, window],
  );
  const handlers = {
    onStartShouldSetResponder: () => true,
    onResponderGrant: (e: GestureResponderEvent) => setAt(toTime(e.nativeEvent.locationX)),
    onResponderMove: (e: GestureResponderEvent) => setAt(toTime(e.nativeEvent.locationX)),
    onResponderRelease: () => setAt(null),
    onResponderTerminate: () => setAt(null),
    // Let the page scroll take over a vertical drag.
    onResponderTerminationRequest: () => true,
    onPointerMove: (e: { nativeEvent: { offsetX?: number; locationX?: number } }) =>
      setAt(toTime(e.nativeEvent.offsetX ?? e.nativeEvent.locationX ?? 0)),
    onPointerLeave: () => setAt(null),
  };
  return { at, handlers };
}

const nearest = (points: Point[], t: number) =>
  points.reduce<Point | null>(
    (best, p) => (p.v !== null && (!best || Math.abs(p.t - t) < Math.abs(best.t - t)) ? p : best),
    null,
  );

// ---------- temperature ----------

type SeriesProps = { rows: Reading[]; window: ChartWindow; tz: string; height?: number };

/** Bedroom temperature through the night, with the comfortable band shaded and the coldest point named. */
export function TemperatureChart({ rows, window, tz, height = 132 }: SeriesProps) {
  const { colors } = useTheme();
  const { width, onLayout } = useWidth();
  const { at, handlers } = useScrub(width - TEMP_AXIS, window);
  const points = useMemo(() => bucket(rows, 'temp_c', window.start, window.end, TEMP_BUCKET_MIN), [rows, window]);
  const values = points.flatMap((p) => (p.v === null ? [] : [p.v]));

  const shape = useMemo(() => {
    if (!width || !values.length) return null;
    const lo = Math.floor(Math.min(...values, COMFORT_C[0]) - 0.5);
    const hi = Math.ceil(Math.max(...values, COMFORT_C[1]) + 0.5);
    const x = scaleLinear()
      .domain([window.start, window.end])
      .range([PAD.left, width - TEMP_AXIS]);
    const y = scaleLinear()
      .domain([lo, hi])
      .range([height - PAD.bottom, PAD.top]);
    const path = line<Point>()
      .defined((p) => p.v !== null)
      .x((p) => x(p.t))
      .y((p) => y(p.v as number))
      .curve(curveMonotoneX)(points);
    const coldest = points.reduce<Point | null>(
      (a, p) => (p.v !== null && (!a || p.v < (a.v as number)) ? p : a),
      null,
    );
    const ticks = y.ticks(3).filter((v) => v > lo && v < hi);
    return { x, y, path, coldest, ticks };
  }, [width, values, points, window, height]);

  const latest = [...points].reverse().find((p) => p.v !== null);
  const scrubbed = at !== null ? nearest(points, at) : null;
  const readout = scrubbed
    ? `${clock(scrubbed.t, tz)}  ${(scrubbed.v as number).toFixed(1)}°C`
    : latest
      ? `Latest ${(latest.v as number).toFixed(1)}°C`
      : 'No readings';
  const summary = shape?.coldest
    ? `Coldest ${(shape.coldest.v as number).toFixed(1)} degrees at ${clock(shape.coldest.t, tz)}.`
    : 'No temperature readings for this night.';

  return (
    <ChartCard title="Bedroom" readout={readout} summary={summary} axisInset={TEMP_AXIS}>
      <View onLayout={onLayout} style={{ height }} {...handlers}>
        {shape ? (
          <Svg width={width} height={height}>
            <Rect
              x={0}
              width={width - TEMP_AXIS}
              y={shape.y(COMFORT_C[1])}
              height={shape.y(COMFORT_C[0]) - shape.y(COMFORT_C[1])}
              rx={6}
              fill={colors['chart-asleep']}
              opacity={0.12}
            />
            {shape.ticks.map((v) => (
              <Line
                key={v}
                x1={0}
                x2={width - TEMP_AXIS}
                y1={shape.y(v)}
                y2={shape.y(v)}
                stroke={colors.hairline}
                strokeWidth={1}
              />
            ))}
            <Path
              d={shape.path ?? ''}
              stroke={colors['chart-line']}
              strokeWidth={2}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {shape.coldest ? (
              <Circle
                cx={shape.x(shape.coldest.t)}
                cy={shape.y(shape.coldest.v as number)}
                r={4}
                fill={colors['chart-line']}
                stroke={colors.surface}
                strokeWidth={2}
              />
            ) : null}
            {scrubbed ? <ScrubMark x={shape.x(scrubbed.t)} y={shape.y(scrubbed.v as number)} height={height} /> : null}
          </Svg>
        ) : (
          <Empty text="No bedroom readings for this night." />
        )}
        {shape ? (
          <View
            pointerEvents="none"
            className="absolute left-0 flex-row gap-3"
            style={{ top: shape.y(COMFORT_C[0]) - 18 }}
          >
            <Text className="pl-1.5 font-sans text-xs text-ink-muted">
              Comfortable {COMFORT_C[0]} to {COMFORT_C[1]}°C
            </Text>
          </View>
        ) : null}
        {shape?.ticks.map((v) => (
          <Text
            key={v}
            pointerEvents="none"
            className="absolute right-0 font-sans text-xs text-ink-muted"
            style={{ top: shape.y(v) - 8 }}
          >
            {v}°
          </Text>
        ))}
      </View>
    </ChartCard>
  );
}

// ---------- movement and the pillow strip ----------

/** How much the pillow moved (a calm area), with a strip under it for when a head was on the pillow. */
export function MovementChart({ rows, window, tz, height = 96 }: SeriesProps) {
  const { colors } = useTheme();
  const { width, onLayout } = useWidth();
  const { at, handlers } = useScrub(width, window);
  const points = useMemo(() => bucket(rows, 'motion', window.start, window.end, MOTION_BUCKET_MIN), [rows, window]);
  const spans = useMemo(() => onPillowSpans(rows), [rows]);
  const strip = 8;
  const plot = height - strip - 8;

  const shape = useMemo(() => {
    if (!width || !points.some((p) => p.v !== null)) return null;
    const x = scaleLinear().domain([window.start, window.end]).range([0, width]).clamp(true);
    const y = scaleLinear().domain([0, 1]).range([plot, PAD.top]);
    const defined = (p: Point) => p.v !== null;
    const fill = area<Point>()
      .defined(defined)
      .x((p) => x(p.t))
      .y0(plot)
      .y1((p) => y(p.v as number))
      .curve(curveMonotoneX)(points);
    const edge = line<Point>()
      .defined(defined)
      .x((p) => x(p.t))
      .y((p) => y(p.v as number))
      .curve(curveMonotoneX)(points);
    return { x, y, fill, edge };
  }, [width, points, window, plot]);

  const scrubbed = at !== null ? nearest(points, at) : null;
  const onPillowAt = (t: number) => spans.some((s) => t >= s.from && t < s.to);
  const level = (v: number) => (v < 0.12 ? 'Still' : v < 0.3 ? 'Shifting' : 'Restless');
  const readout = scrubbed
    ? `${clock(scrubbed.t, tz)}  ${onPillowAt(scrubbed.t) ? level(scrubbed.v as number) : 'Off the pillow'}`
    : `On the pillow ${Math.round(spans.reduce((m, s) => m + (s.to - s.from), 0) / 60_000 / 6) / 10}h`;

  return (
    <ChartCard
      title="Movement"
      readout={readout}
      summary="How much the pillow moved through the night, and when a head was on it."
    >
      <View onLayout={onLayout} style={{ height }} {...handlers}>
        {shape ? (
          <Svg width={width} height={height}>
            <Line x1={0} x2={width} y1={plot} y2={plot} stroke={colors.hairline} strokeWidth={1} />
            <Path d={shape.fill ?? ''} fill={colors['chart-restless']} opacity={0.16} />
            <Path
              d={shape.edge ?? ''}
              stroke={colors['chart-restless']}
              strokeWidth={2}
              fill="none"
              strokeLinejoin="round"
            />
            <G>
              <Rect
                x={0}
                y={height - strip}
                width={width}
                height={strip}
                rx={strip / 2}
                fill={colors.ink}
                opacity={0.08}
              />
              {spans.map((s, i) => {
                const x0 = shape.x(s.from);
                const x1 = shape.x(s.to);
                return x1 - x0 < 1 ? null : (
                  <Rect
                    key={i}
                    x={x0}
                    y={height - strip}
                    width={x1 - x0}
                    height={strip}
                    rx={strip / 2}
                    fill={colors['chart-asleep']}
                  />
                );
              })}
            </G>
            {scrubbed ? <ScrubMark x={shape.x(scrubbed.t)} y={shape.y(scrubbed.v as number)} height={height} /> : null}
          </Svg>
        ) : (
          <Empty text="No movement readings for this night." />
        )}
      </View>
      <View className="mt-1 flex-row items-center gap-1.5">
        <View className="h-2 w-4 rounded-full" style={{ backgroundColor: colors['chart-asleep'] }} />
        <Text className="font-sans text-xs text-ink-muted">Head on the pillow</Text>
      </View>
    </ChartCard>
  );
}

function ScrubMark({ x, y, height }: { x: number; y: number; height: number }) {
  const { colors } = useTheme();
  return (
    <G>
      <Line x1={x} x2={x} y1={0} y2={height} stroke={colors.ink} strokeOpacity={0.35} strokeWidth={1} />
      <Circle cx={x} cy={y} r={4.5} fill={colors.ink} stroke={colors.surface} strokeWidth={2} />
    </G>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <View className="flex-1 items-center justify-center rounded-xl border border-dashed border-hairline">
      <Text className="font-sans text-sm text-ink-muted">{text}</Text>
    </View>
  );
}

// ---------- how the night was spent ----------

const SHARE_KINDS = [
  { key: 'asleep', label: 'Asleep', token: 'chart-asleep' },
  { key: 'restless', label: 'Restless', token: 'chart-restless' },
  { key: 'up', label: 'Out of bed', token: 'chart-up' },
] as const;

/** Minutes asleep, restless and out of bed, from the ribbon's segments. */
export function nightShare(segments: readonly RibbonSegment[]) {
  const hours = (kind: RibbonSegment['kind']) =>
    segments.filter((s) => s.kind === kind).reduce((h, s) => h + s.to - s.from, 0);
  const restless = hours('restless');
  return {
    asleep: Math.max(0, hours('bed') - restless) * 60,
    restless: restless * 60,
    up: (hours('up') + hours('alert')) * 60,
  };
}

/** Minutes as "7h 05m"-style words: "7h 5m", or "40m" under an hour. */
export const hm = (min: number) => {
  const m = Math.round(min);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
};

/** A donut of the night, with its legend as rows that carry the numbers. */
export function NightShareChart({ segments }: { segments: readonly RibbonSegment[] }) {
  const { colors } = useTheme();
  const share = nightShare(segments);
  const total = share.asleep + share.restless + share.up;
  const size = 132;
  const slices = useMemo(() => {
    const data = SHARE_KINDS.map((k) => ({ ...k, value: share[k.key] })).filter((d) => d.value > 0);
    const arcs = pie<(typeof data)[number]>()
      .value((d) => d.value)
      .sort(null)
      .padAngle(0.03)(data);
    const draw = arc<(typeof arcs)[number]>()
      .innerRadius(size / 2 - 16)
      .outerRadius(size / 2)
      .cornerRadius(4);
    return arcs.map((a) => ({ key: a.data.key, d: draw(a) ?? '', token: a.data.token }));
  }, [share.asleep, share.restless, share.up]); // eslint-disable-line react-hooks/exhaustive-deps

  const asleepPct = total ? Math.round((share.asleep / total) * 100) : 0;
  return (
    <View
      className="gap-3 rounded-card bg-surface p-[18px]"
      accessible
      accessibilityLabel={`How the night was spent: asleep ${hm(share.asleep)}, restless ${hm(share.restless)}, out of bed ${hm(share.up)}.`}
    >
      <Text className="font-display text-lg text-ink">How the night was spent</Text>
      {total ? (
        <View className="flex-row items-center gap-5">
          <View style={{ width: size, height: size }}>
            <Svg width={size} height={size}>
              <G x={size / 2} y={size / 2}>
                {slices.map((s) => (
                  <Path key={s.key} d={s.d} fill={colors[s.token]} />
                ))}
              </G>
            </Svg>
            <View className="absolute inset-0 items-center justify-center">
              <Text className="font-sans-semibold text-2xl text-ink">{asleepPct}%</Text>
              <Text className="font-sans text-xs text-ink-muted">asleep</Text>
            </View>
          </View>
          <View className="flex-1 gap-3">
            {SHARE_KINDS.map((k) => (
              <View key={k.key} className="flex-row items-center gap-2.5">
                <View className="h-3 w-3 rounded-[4px]" style={{ backgroundColor: colors[k.token] }} />
                <Text className="flex-1 font-sans text-sm text-ink">{k.label}</Text>
                <Text className="font-sans-semibold text-sm text-ink">{hm(share[k.key])}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : (
        <Text className="font-sans text-sm text-ink-muted">Nothing from the pillow that night.</Text>
      )}
    </View>
  );
}

// ---------- the week at a glance ----------

export type WeekBar = {
  key: number;
  /** Shown under the column; may be empty on a dense chart. */
  label: string;
  /** Read out by screen readers when the label is empty or short. */
  name?: string;
  hours: number | null;
  flagged: boolean;
  onPress: () => void;
};

/**
 * Hours asleep per night as columns, oldest on the left; a night with an alert gets the amber cap. Tap one to open
 * it. `dense` draws thin columns for a month, labelling only the bars that carry a label.
 */
export function WeekSleepChart({
  bars,
  title = 'Sleep this week',
  dense = false,
}: {
  bars: WeekBar[];
  title?: string;
  dense?: boolean;
}) {
  const { colors } = useTheme();
  const height = 112;
  const max = Math.max(9, ...bars.map((b) => b.hours ?? 0));
  const avg = bars.filter((b) => b.hours !== null);
  const mean = avg.length ? avg.reduce((s, b) => s + (b.hours as number), 0) / avg.length : null;
  return (
    <View className="gap-3 rounded-card bg-surface p-[18px]" accessible={false}>
      <View className="flex-row items-baseline justify-between">
        <Text className="font-display text-lg text-ink">{title}</Text>
        {mean !== null ? <Text className="font-sans text-sm text-ink-muted">Average {hm(mean * 60)}</Text> : null}
      </View>
      <View className="flex-row items-end justify-between" style={{ height: height + 22 }}>
        {bars.map((b) => {
          const h = b.hours === null ? 0 : Math.max(6, (b.hours / max) * height);
          return (
            <Pressable
              key={b.key}
              onPress={b.onPress}
              accessibilityRole="button"
              accessibilityLabel={`${b.name ?? b.label}: ${b.hours === null ? 'no reading' : `${hm(b.hours * 60)} asleep`}${b.flagged ? ', family alerted' : ''}`}
              className="flex-1 items-center gap-1.5"
              hitSlop={dense ? 0 : 4}
            >
              <View className="w-full items-center justify-end" style={{ height }}>
                {b.hours === null ? (
                  <View
                    className={`h-1.5 rounded-full ${dense ? 'w-1.5' : 'w-5'}`}
                    style={{ backgroundColor: colors.hairline }}
                  />
                ) : (
                  <View
                    className={`overflow-hidden ${dense ? 'w-1.5 rounded-t-[3px]' : 'w-5 rounded-t-[4px]'}`}
                    style={{ height: h, backgroundColor: colors['chart-asleep'] }}
                  >
                    {b.flagged ? <View style={{ height: dense ? 5 : 6, backgroundColor: colors['chart-up'] }} /> : null}
                  </View>
                )}
              </View>
              {dense ? null : <Text className="font-sans text-xs text-ink-muted">{b.label}</Text>}
            </Pressable>
          );
        })}
      </View>
      {dense ? (
        // A month's columns are too thin to label one by one: a date for each week instead.
        <View className="-mt-5 flex-row justify-between">
          {bars
            .filter((b) => b.label)
            .map((b) => (
              <Text key={b.key} className="font-sans text-xs text-ink-muted">
                {b.label}
              </Text>
            ))}
        </View>
      ) : null}
    </View>
  );
}
