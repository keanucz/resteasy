import { useId } from 'react';
import { Text, View } from 'react-native';
import Svg, { ClipPath, Defs, G, Pattern, Rect } from 'react-native-svg';

import { useTheme } from '@/hooks/useTheme';

/** Night window the ribbon spans: 10 pm to 7 am. */
const NIGHT_HOURS = 9;
const TRACK_HEIGHT = 18;

export type RibbonKind = 'bed' | 'restless' | 'up' | 'alert' | 'unknown';

export type RibbonSegment = {
  kind: RibbonKind;
  /** Hours after 10 pm. */
  from: number;
  to: number;
};

type NightRibbonProps = {
  segments: readonly RibbonSegment[];
  /** Hours after 10 pm; draws the "now" line. */
  now?: number;
};

const pct = (hours: number) => `${(Math.min(Math.max(hours, 0), NIGHT_HOURS) / NIGHT_HOURS) * 100}%`;

/** The night so far, 10 pm to 7 am: solid in bed, hatched when restless, a thin bar when up. */
export function NightRibbon({ segments, now }: NightRibbonProps) {
  const { colors } = useTheme();
  const id = useId().replace(/:/g, '');
  const fill: Record<RibbonKind, string> = {
    bed: colors['state-asleep'],
    restless: `url(#${id}-restless)`,
    up: colors['state-up'],
    alert: colors['state-alert'],
    unknown: `url(#${id}-unknown)`,
  };
  // Being up or needing help draws a thinner bar, so it reads as "out of bed", not more sleep.
  const inset: Record<RibbonKind, number> = { bed: 5, restless: 5, up: 7, alert: 7, unknown: 5 };
  return (
    <View className="gap-1.5">
      <Svg width="100%" height={TRACK_HEIGHT}>
        <Defs>
          <ClipPath id={`${id}-track`}>
            <Rect x="0" y="0" width="100%" height={TRACK_HEIGHT} rx={TRACK_HEIGHT / 2} />
          </ClipPath>
          <Pattern id={`${id}-restless`} patternUnits="userSpaceOnUse" width="8" height="8" patternTransform="rotate(45)">
            <Rect width="4" height="8" fill={colors['state-restless']} />
          </Pattern>
          <Pattern id={`${id}-unknown`} patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
            <Rect width="2" height="7" fill={colors['ink-muted']} />
          </Pattern>
        </Defs>
        <G clipPath={`url(#${id}-track)`}>
          <Rect x="0" y="0" width="100%" height={TRACK_HEIGHT} fill={colors.ink} opacity={0.08} />
          {segments.map((s, i) => (
            <Rect
              key={i}
              x={pct(s.from)}
              y={inset[s.kind]}
              width={pct(s.to - s.from)}
              height={TRACK_HEIGHT - inset[s.kind] * 2}
              fill={fill[s.kind]}
              opacity={s.kind === 'unknown' ? 0.7 : 0.9}
            />
          ))}
          {now !== undefined ? <Rect x={pct(now)} y="0" width="2" height={TRACK_HEIGHT} fill={colors.ink} /> : null}
        </G>
      </Svg>
      <View className="flex-row justify-between">
        <Text className="font-sans text-[11px] text-ink-muted">10 pm</Text>
        <Text className="font-sans text-[11px] text-ink-muted">7 am</Text>
      </View>
    </View>
  );
}
