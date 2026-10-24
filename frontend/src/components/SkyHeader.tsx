import { type PropsWithChildren, useId, useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Defs, G, LinearGradient, Mask, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

import { PhotoRing } from '@/components/PhotoRing';
import { StatusHeadline } from '@/components/Status';
import { SKY, SKY_DETAIL, SKY_LOOKS, STARRY_STATES } from '@/constants/sky';
import type { PillowState } from '@/constants/status';
import { useTheme } from '@/hooks/useTheme';

const EDGE_SAMPLES = 48;
const FADE_BANDS = 16;
const STAR_COLS = 9;
const STAR_ROWS = 6;
/** Stars stop this far above the highest point of the edge, so they never trace the curve. */
const STAR_CLEARANCE = 24;

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
  return values.map((v, i) => [(i / EDGE_SAMPLES) * width, horizon - (hi - lo < 1e-9 ? 0 : (v - lo) / (hi - lo)) * rise]);
}

const line = (points: [number, number][]) => points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L');

type SkyBackdropProps = PropsWithChildren<{
  state: PillowState;
  /** px from below the status bar to the lowest point of the edge. */
  horizon?: number;
}>;

/**
 * The sky in a state's colours: gradient, glow, stars, and a curved bottom edge that fades into
 * the page. Children sit on top, starting below the status bar. Used by SkyHeader and the login.
 */
export function SkyBackdrop({ state, horizon: horizonProp = SKY.horizon, children }: SkyBackdropProps) {
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
      return { d: `M0,0 L${width},0 L${line(lowered.reverse())} Z`, opacity: 1 - (1 - target(k)) / (1 - target(k + 1)) };
    });
    const ceiling = Math.max(1, Math.min(...edge.map(([, y]) => y)) - STAR_CLEARANCE);
    const rnd = seeded(7);
    const stars: { x: number; y: number; r: number; o: number }[] = [];
    for (let r = 0; r < STAR_ROWS; r++) {
      for (let c = 0; c < STAR_COLS; c++) {
        if (rnd() < 0.35) continue; // gaps, so it never reads as a grid
        const x = ((c + 0.1 + rnd() * 0.8) / STAR_COLS) * width;
        const y = ((r + 0.1 + rnd() * 0.8) / STAR_ROWS) * ceiling;
        const big = rnd() < 0.12;
        stars.push({ x, y, r: big ? 1.4 : 0.5 + rnd() * 0.6, o: (big ? 0.95 : 0.3 + rnd() * 0.5) * (1 - smoothstep(y / ceiling) * 0.85) });
      }
    }
    return { sky, bands, stars };
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
          {showStars ? shapes.stars.map((s, i) => <Circle key={i} cx={s.x} cy={s.y} r={s.r} fill="#FFFFFF" opacity={s.o} />) : null}
        </Svg>
      ) : null}
      <View style={{ paddingTop: insets.top }}>{children}</View>
    </View>
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
};

/**
 * Top of the home screen: the sky with the status as its headline. The stats placed after it sit
 * where the fade ends.
 */
export function SkyHeader({ state, name, initials, photoUri, detail }: SkyHeaderProps) {
  const { scheme } = useTheme();
  const ink = SKY_LOOKS[state][scheme].ink;
  return (
    <SkyBackdrop state={state}>
      <View className="flex-row items-start gap-3.5 px-[22px] pt-8">
        <PhotoRing state={state} initials={initials} photoUri={photoUri} />
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
}
