import { memo, type PropsWithChildren, type ReactNode, useEffect, useId, useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, G, LinearGradient, Mask, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

import { Hedgehog, type HedgehogMood } from '@/components/Hedgehog';
import { PhotoRing } from '@/components/PhotoRing';
import { StatusHeadline } from '@/components/Status';
import { SKY, SKY_DETAIL, SKY_LOOKS, STARRY_STATES } from '@/constants/sky';
import { fonts } from '@/constants/theme';
import type { PillowState } from '@/constants/status';
import { useTheme } from '@/hooks/useTheme';

const EDGE_SAMPLES = 48;
const FADE_BANDS = 16;
const STAR_COLS = 9;
const STAR_ROWS = 6;
/** Stars stop this far above the highest point of the edge, so they never trace the curve. */
const STAR_CLEARANCE = 24;
/**
 * The stars turn slowly around a pole this far above the top of the screen, like the night sky
 * around the pole star: one turn every few minutes, so it is felt more than seen.
 */
const STAR_POLE_ABOVE = 120;
const STAR_TURN_MS = 5 * 60 * 1000;
/** Smallest star cell, so a shallow sky never asks for thousands of rows. */
const STAR_MIN_CELL = 12;
/** The hedgehog that walks the arch through the night, and how far from each end it starts and stops. */
const HEDGEHOG_SIZE = 68;
const HEDGEHOG_HEIGHT = (HEDGEHOG_SIZE * 38) / 56;
const HEDGEHOG_INSET = 34;
/** One lap of the arch, edge to edge, and one hop of it: a slow amble with a light, even bounce. */
const HEDGEHOG_LAP_MS = 22_000;
const HEDGEHOG_HOP_MS = 520;
const HEDGEHOG_HOP_PX = 7;
/** While she sleeps it curls up mid-arch; restless, it fidgets there (degrees either way). */
const HEDGEHOG_FIDGET_DEG = 5;
const HEDGEHOG_FIDGET_MS = 260;
/** Each "z" rises this far (kept below the headline and detail text) over one cycle, three in turn. */
const SNORE_RISE_PX = 26;
const SNORE_DRIFT_PX = 12;
const SNORE_CYCLE_MS = 2700;
const SNORE_LETTERS = 3;
/** Where it sets out from when there is no night to walk (daytime). */
const HEDGEHOG_IDLE = 0.5;
/**
 * The hedgehog keeps her company while all is well: asleep, fidgety when she's restless, on its
 * feet when she's up. It stays away for an alert (something may really be wrong) and offline.
 */
const HEDGEHOG_MOODS: Partial<Record<PillowState, HedgehogMood>> = {
  asleep: 'asleep',
  restless: 'restless',
  up: 'awake',
};
/** The edge melts over the fade, so the horizon the eye sees sits this far into it. */
const HEDGEHOG_SINK = SKY.fadeLength * 0.4;

const smoothstep = (t: number) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));

/** Small deterministic random generator, so the stars stay put between renders. */
function seeded(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** y of the sky's bottom edge at each sample, given the canvas width and the horizon line. */
function edgePoints(width: number, horizon: number): [number, number][] {
  const values = Array.from({ length: EDGE_SAMPLES + 1 }, (_, i) => SKY.edge((i / EDGE_SAMPLES) * 2 - 1));
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const rise = SKY.archHeight * SKY.horizon; // same arch on every sky, whatever its horizon
  return values.map((v, i) => [
    (i / EDGE_SAMPLES) * width,
    horizon - (hi - lo < 1e-9 ? 0 : (v - lo) / (hi - lo)) * rise,
  ]);
}

const line = (points: [number, number][]) => points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');

type SkyBackdropProps = PropsWithChildren<{
  state: PillowState;
  /** px from below the status bar to the lowest point of the edge. */
  horizon?: number;
  /** 0 to 1 through the night: the hedgehog walks the arch from 10 pm (left) to 7 am (right). */
  traveller?: number;
  /** How the hedgehog looks; it only appears with a `traveller`. */
  mood?: HedgehogMood;
  /** Something that sits still on the edge (the Reminders hedgehog): how far along, 0 to 1, and its box. */
  perch?: { at: number; width: number; height: number; node: ReactNode };
}>;

/**
 * The sky in a state's colours: gradient, glow, stars, and a curved bottom edge that fades into
 * the page. Children sit on top, starting below the status bar. Used by SkyHeader and the login.
 */
export function SkyBackdrop({
  state,
  horizon: horizonProp = SKY.horizon,
  traveller,
  mood = 'asleep',
  perch,
  children,
}: SkyBackdropProps) {
  const { scheme } = useTheme();
  const insets = useSafeAreaInsets();
  const id = useId().replace(/:/g, ''); // unique SVG ids, so two skies on one page don't clash
  const [width, setWidth] = useState(0);
  const look = SKY_LOOKS[state][scheme];
  const horizon = insets.top + horizonProp;
  const height = horizon + SKY.fadeLength;

  const shapes = useMemo(() => {
    if (!width) return null;
    const edge = edgePoints(width, horizon);
    const sky = `M0,0 L${width},0 L${line([...edge].reverse())} Z`;
    // The fade is a stack of nested copies of the sky, each reaching one step lower. They overlap
    // rather than tile, so there are no seams; each copy's opacity is picked so the stack adds up
    // to a smoothstep fade.
    const step = SKY.fadeLength / FADE_BANDS;
    const target = (k: number) => (k > FADE_BANDS ? 0 : 1 - smoothstep((k - 0.5) / FADE_BANDS));
    const bands = Array.from({ length: FADE_BANDS }, (_, i) => {
      const k = i + 1;
      const lowered = edge.map(([x, y]) => [x, y + k * step] as [number, number]);
      return {
        d: `M0,0 L${width},0 L${line(lowered.reverse())} Z`,
        opacity: 1 - (1 - target(k)) / (1 - target(k + 1)),
      };
    });
    const ceiling = Math.max(1, Math.min(...edge.map(([, y]) => y)) - STAR_CLEARANCE);
    return { sky, bands, ceiling, edge };
  }, [width, horizon]);

  const showStars = SKY.stars && scheme === 'dark' && STARRY_STATES.includes(state);

  return (
    <View style={{ height }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {shapes ? (
        <Svg width={width} height={height} style={{ position: 'absolute' }} accessible={false}>
          <Defs>
            <LinearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2={horizon} gradientUnits="userSpaceOnUse">
              <Stop offset="0" stopColor={look.sky[0]} />
              <Stop offset="1" stopColor={look.sky[1]} />
            </LinearGradient>
            {look.glow ? (
              <RadialGradient
                id={`${id}-glow`}
                cx={look.glow.x * width}
                cy={horizon}
                r={look.glow.r * width}
                gradientUnits="userSpaceOnUse"
              >
                <Stop offset="0" stopColor={look.glow.color} stopOpacity={look.glow.opacity} />
                <Stop offset="1" stopColor={look.glow.color} stopOpacity={0} />
              </RadialGradient>
            ) : null}
            <Mask id={`${id}-mask`} maskUnits="userSpaceOnUse" x="0" y="0" width={width} height={height}>
              <Path d={shapes.sky} fill="#FFFFFF" />
              {shapes.bands.map((b, i) => (
                <Path key={i} d={b.d} fill="#FFFFFF" fillOpacity={b.opacity} />
              ))}
            </Mask>
          </Defs>
          <G mask={`url(#${id}-mask)`}>
            <Rect x="0" y="0" width={width} height={height} fill={`url(#${id}-fill)`} />
            {look.glow ? <Rect x="0" y="0" width={width} height={height} fill={`url(#${id}-glow)`} /> : null}
          </G>
        </Svg>
      ) : null}
      {shapes && showStars ? <StarField width={width} ceiling={shapes.ceiling} /> : null}
      <View style={{ paddingTop: insets.top }}>{children}</View>
      {shapes && traveller !== undefined ? (
        <Traveller edge={shapes.edge} width={width} progress={traveller} mood={mood} ink={SKY_DETAIL[scheme]} />
      ) : null}
      {shapes && perch ? <Perch edge={shapes.edge} x={perch.at * width} {...perch} /> : null}
    </View>
  );
}

/**
 * The stars, turning slowly around the pole above the screen, kept to the sky above the edge.
 * Under reduced motion they hold still.
 */
const StarField = memo(function StarField({
  width,
  ceiling,
}: {
  width: number;
  /** How far down the sky the stars may show. */
  ceiling: number;
}) {
  const reduced = useReducedMotion();
  // A disc of stars around the pole, big enough that the sky is covered at every angle of the turn.
  // Its middle (nearer the pole than the top of the screen) is never seen, so it stays empty.
  const { list, reach } = useMemo(() => {
    const reach = Math.ceil(Math.hypot(width / 2, ceiling + STAR_POLE_ABOVE));
    const cellW = width / STAR_COLS;
    const cellH = Math.max(ceiling / STAR_ROWS, STAR_MIN_CELL);
    const rnd = seeded(7);
    const list: { x: number; y: number; r: number; o: number }[] = [];
    for (let r = 0; r < Math.ceil((reach * 2) / cellH); r++) {
      for (let c = 0; c < Math.ceil((reach * 2) / cellW); c++) {
        if (rnd() < 0.35) continue; // gaps, so it never reads as a grid
        const x = (c + 0.1 + rnd() * 0.8) * cellW;
        const y = (r + 0.1 + rnd() * 0.8) * cellH;
        const big = rnd() < 0.12;
        const size = big ? 1.4 : 0.5 + rnd() * 0.6;
        const glow = big ? 0.95 : 0.3 + rnd() * 0.5;
        // How far below the top of the sky this star passes at its lowest: fainter towards the horizon.
        const depth = Math.hypot(x - reach, y - reach) - STAR_POLE_ABOVE;
        if (depth < 0 || depth > reach) continue;
        list.push({ x, y, r: size, o: glow * (1 - smoothstep(depth / ceiling) * 0.85) });
      }
    }
    return { list, reach };
  }, [width, ceiling]);
  const turn = useSharedValue(0);

  useEffect(() => {
    turn.set(0);
    if (reduced) return;
    // Anticlockwise, the way the sky turns around the pole star.
    turn.set(withRepeat(withTiming(-360, { duration: STAR_TURN_MS, easing: Easing.linear }), -1, false));
    return () => cancelAnimation(turn);
  }, [reduced, turn]);

  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${turn.get()}deg` }] }));

  return (
    <View
      pointerEvents="none"
      style={{ position: 'absolute', left: 0, top: 0, width, height: ceiling, overflow: 'hidden' }}
    >
      <Animated.View
        style={[
          {
            position: 'absolute',
            left: width / 2 - reach,
            top: -STAR_POLE_ABOVE - reach,
            width: reach * 2,
            height: reach * 2,
          },
          style,
        ]}
      >
        <Svg width={reach * 2} height={reach * 2} accessible={false}>
          {list.map((s, i) => (
            <Circle key={i} cx={s.x} cy={s.y} r={s.r} fill="#FFFFFF" opacity={s.o} />
          ))}
        </Svg>
      </Animated.View>
    </View>
  );
});

/**
 * Where on the edge `x` falls, and the edge's slope there in degrees. Past either end it carries on
 * along the end's slope, so the hedgehog comes on and goes off already tilted to the curve.
 */
function onEdge(edge: number[][], x: number): { y: number; angle: number } {
  'worklet';
  const last = edge.length - 1;
  const i =
    x <= edge[0][0] ? 0 : x >= edge[last][0] ? last - 1 : Math.min(last - 1, Math.floor((x / edge[last][0]) * last));
  const [x0, y0] = edge[i];
  const [x1, y1] = edge[i + 1];
  const slope = x1 === x0 ? 0 : (y1 - y0) / (x1 - x0);
  return { y: y0 + slope * (x - x0), angle: (Math.atan(slope) * 180) / Math.PI };
}

/** A still companion standing on the edge at `x`, tilted to the curve and sunk into the fade like the traveller. */
function Perch({
  edge,
  x,
  width,
  height,
  node,
}: {
  edge: [number, number][];
  x: number;
  width: number;
  height: number;
  node: ReactNode;
}) {
  const { y, angle } = onEdge(edge, x);
  return (
    <View
      pointerEvents="none"
      style={{
        position: 'absolute',
        left: x - width / 2,
        top: y + HEDGEHOG_SINK - height,
        width,
        height,
        transform: [{ rotate: `${angle}deg` }],
      }}
    >
      {node}
    </View>
  );
}

/**
 * The hedgehog on the arch. Up and about, it hops left to right with a light, even bounce, off the
 * right edge and back in from the left, setting out from its place in the night. In bed it stays
 * curled up mid-arch: breathing slowly and snoring little z's while asleep, fidgeting while
 * restless. Under reduced motion it sits still.
 */
const Traveller = memo(function Traveller({
  edge,
  width,
  progress,
  mood,
  ink,
}: {
  edge: [number, number][];
  width: number;
  progress: number;
  mood: HedgehogMood;
  /** Colour of the z's: the sky's own detail text colour. */
  ink: string;
}) {
  const reduced = useReducedMotion();
  const walking = mood === 'awake';
  const start = walking ? Math.min(1, Math.max(0, progress)) : 0.5;
  const lap = useSharedValue(0);
  const hop = useSharedValue(0);

  useEffect(() => {
    lap.set(0);
    hop.set(0);
    if (reduced || mood === 'asleep') return;
    if (walking) {
      lap.set(withRepeat(withTiming(1, { duration: HEDGEHOG_LAP_MS, easing: Easing.linear }), -1, false));
      hop.set(withRepeat(withTiming(1, { duration: HEDGEHOG_HOP_MS, easing: Easing.linear }), -1, false));
    } else {
      hop.set(withRepeat(withTiming(1, { duration: HEDGEHOG_FIDGET_MS, easing: Easing.inOut(Easing.sin) }), -1, true));
    }
    return () => {
      cancelAnimation(lap);
      cancelAnimation(hop);
    };
  }, [reduced, walking, mood, lap, hop]);

  const style = useAnimatedStyle(() => {
    // The lap runs from just off the left edge to just off the right one.
    const from = -HEDGEHOG_SIZE;
    const span = width + HEDGEHOG_SIZE * 2;
    const home = walking ? HEDGEHOG_INSET + start * (width - HEDGEHOG_INSET * 2) : width / 2;
    const x = walking && !reduced ? from + (((home - from) / span + lap.get()) % 1) * span : home;
    const { y, angle } = onEdge(edge, x);
    const h = hop.get();
    // Walking: a ball's bounce, a parabola each hop, always the same height. Restless: a fidget.
    const lift = walking && !reduced ? 4 * HEDGEHOG_HOP_PX * h * (1 - h) : 0;
    const fidget = mood === 'restless' && !reduced ? (h * 2 - 1) * HEDGEHOG_FIDGET_DEG : 0;
    return {
      transform: [
        { translateX: x - HEDGEHOG_SIZE / 2 },
        { translateY: y + HEDGEHOG_SINK - HEDGEHOG_HEIGHT - lift },
        { rotate: `${angle + fidget}deg` },
      ],
    };
  });

  return (
    <Animated.View pointerEvents="none" style={[{ position: 'absolute', left: 0, top: 0 }, style]}>
      {mood === 'asleep' && !reduced
        ? Array.from({ length: SNORE_LETTERS }, (_, i) => <Snore key={i} index={i} color={ink} />)
        : null}
      <Hedgehog size={HEDGEHOG_SIZE} mood={mood} breathing />
    </Animated.View>
  );
});

/** One "z" of the snore: rises from the hedgehog's head, drifting right, growing and fading. */
function Snore({ index, color }: { index: number; color: string }) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.set(
      withDelay(
        (index * SNORE_CYCLE_MS) / SNORE_LETTERS,
        withRepeat(withTiming(1, { duration: SNORE_CYCLE_MS, easing: Easing.out(Easing.quad) }), -1, false),
      ),
    );
    return () => cancelAnimation(t);
  }, [index, t]);
  const style = useAnimatedStyle(() => {
    const v = t.get();
    return {
      opacity: v < 0.2 ? v / 0.2 : 1 - (v - 0.2) / 0.8,
      transform: [{ translateX: v * SNORE_DRIFT_PX }, { translateY: -v * SNORE_RISE_PX }, { scale: 0.8 + v * 0.5 }],
    };
  });
  return (
    <Animated.Text
      style={[
        { position: 'absolute', left: HEDGEHOG_SIZE * 0.66, top: -4, color, fontFamily: fonts.sans, fontSize: 13 },
        style,
      ]}
    >
      z
    </Animated.Text>
  );
}

type SkyHeaderProps = {
  state: PillowState;
  /** Who the pillow belongs to: "Mum". */
  name: string;
  initials: string;
  photoUri?: string;
  /** The line under the headline: "In bed since 10:42 pm." */
  detail?: string;
  /** 0 to 1 through the night: the hedgehog's place on the arch. Outside the night it waits mid-arch. */
  nightProgress?: number;
  /** When set, the photo becomes a button (with a small chevron) that opens the people switcher. */
  onSwitchPerson?: () => void;
};

/**
 * Top of the home screen: the sky with the status as its headline. The stats placed after it sit
 * where the fade ends.
 */
export const SkyHeader = memo(function SkyHeader({ state, name, initials, photoUri, detail, nightProgress, onSwitchPerson }: SkyHeaderProps) {
  const { scheme } = useTheme();
  const ink = SKY_LOOKS[state][scheme].ink;
  return (
    <SkyBackdrop
      state={state}
      traveller={HEDGEHOG_MOODS[state] ? (nightProgress ?? HEDGEHOG_IDLE) : undefined}
      mood={HEDGEHOG_MOODS[state]}
    >
      <View className="flex-row items-start gap-3.5 px-[22px] pt-8">
        {onSwitchPerson ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Showing ${name}. Switch person`}
            onPress={onSwitchPerson}
            hitSlop={8}
            className="active:opacity-80"
          >
            <PhotoRing state={state} initials={initials} photoUri={photoUri} />
            <View
              className="absolute bottom-0 right-0 size-6 items-center justify-center rounded-full bg-surface"
              style={{ borderWidth: 2, borderColor: SKY_LOOKS[state][scheme].ink + '33' }}
            >
              <Svg width={12} height={12} viewBox="0 0 24 24" accessible={false}>
                <Path
                  d="M6 9 L12 15 L18 9"
                  stroke={SKY_DETAIL[scheme]}
                  strokeWidth={2.6}
                  fill="none"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </Svg>
            </View>
          </Pressable>
        ) : (
          <PhotoRing state={state} initials={initials} photoUri={photoUri} />
        )}
        <View className="flex-1 pt-1">
          <StatusHeadline state={state} name={name} wordColor={ink} />
          {detail ? (
            <Text className="mt-3 font-sans text-sm" style={{ color: SKY_DETAIL[scheme] }}>
              {detail}
            </Text>
          ) : null}
        </View>
      </View>
    </SkyBackdrop>
  );
});
