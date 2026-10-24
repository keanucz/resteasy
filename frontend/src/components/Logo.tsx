import { useId } from 'react';
import Svg, { Circle, ClipPath, Defs, Ellipse, G, LinearGradient, Path, Stop } from 'react-native-svg';

import { logoColors, palette } from '@/constants/theme';

/** The pillow badge's outline; the art is clipped to a slightly smaller copy so a thin navy seam frames it. */
const PILLOW =
  'M22 14 C80 24 160 24 218 14 C226 12 230 16 228 24 C220 70 220 110 228 156 C230 164 226 168 218 166 ' +
  'C160 156 80 156 22 166 C14 168 10 164 12 156 C20 110 20 70 12 24 C10 16 14 12 22 14 Z';

/** Any fixed Tailwind colour name: the `logo-*` tokens, or the palette's own (glow, mist, night ...). */
const COLOURS = { ...palette, ...logoColors };
export type LogoColour = keyof typeof COLOURS;

/** Which token paints each part of the mark. Recolour the mark in palette.js, not here. */
const PARTS = {
  skyTop: 'logo-sky-top',
  skyBottom: 'logo-sky-bottom',
  spines: 'logo-spines',
  face: 'logo-face',
  ink: 'logo-ink',
  cheek: 'logo-cheek',
  blanket: 'logo-blanket',
  fold: 'logo-fold',
  sparkle: 'logo-sparkle',
  sparkleSmall: 'logo-sparkle-small',
} satisfies Record<string, LogoColour>;

export type LogoPart = keyof typeof PARTS;

type LogoProps = {
  /** Width in px; the height follows the badge's 4:3 shape. */
  size?: number;
  /** Per-instance overrides by Tailwind colour name, e.g. `{ spines: 'glow' }`. */
  tint?: Partial<Record<LogoPart, LogoColour>>;
  /** Colour of a 1.5px hairline around the badge, for skies as dark as the badge itself. */
  outline?: string;
};

/**
 * The Rest Easy mark: a sleepy hedgehog tucked under a blanket inside a pillow, with two sparkles.
 * Its colours are the `logo-*` tokens in palette.js (also Tailwind's fill-logo-* classes), the same
 * in Light and Dark mode. They go in as props because react-native-svg on web drops className.
 */
export function Logo({ size = 120, tint, outline }: LogoProps) {
  const id = useId().replace(/:/g, ''); // unique SVG ids, so two logos on one screen don't clash
  const c = Object.fromEntries(
    Object.entries(PARTS).map(([part, token]) => [part, COLOURS[tint?.[part as LogoPart] ?? token]]),
  ) as Record<LogoPart, string>;
  return (
    <Svg width={size} height={(size * 180) / 240} viewBox="0 0 240 180" accessibilityRole="image" accessibilityLabel="Rest Easy">
      <Defs>
        <LinearGradient id={`${id}-sky`} x1="0" y1="0" x2="0.4" y2="1">
          <Stop offset="0" stopColor={c.skyTop} />
          <Stop offset="1" stopColor={c.skyBottom} />
        </LinearGradient>
        <ClipPath id={`${id}-inset`}>
          <Path d={PILLOW} transform="translate(120 90) scale(0.95 0.93) translate(-120 -90)" />
        </ClipPath>
      </Defs>
      {/* 1.5px on screen, whatever the size: the viewBox is 240 units wide. */}
      <Path d={PILLOW} fill={`url(#${id}-sky)`} stroke={outline} strokeWidth={outline ? (1.5 * 240) / size : 0} />
      <G clipPath={`url(#${id}-inset)`}>
        <G transform="translate(20 -15)">
          {/* Spines: the full round back, tucked in. */}
          <Path
            d="M18 212 L18.0 149.8 L1.1 155.4 L20.7 133.8 L2.9 134.7 L27.5 118.9 L10.1 115.2 L38.0 106.4 L22.1 98.2 L51.3 97.0 L38.1 85.0 L66.6 91.5 L57.0 76.4 L82.9 90.1 L77.5 73.0 L98.9 93.0 L98.2 75.1 L113.7 99.9 L117.6 82.5 L130 108 C118 124 112 150 110 212 L0 212 Z"
            fill={c.spines}
            stroke={c.spines}
            strokeWidth={6}
            strokeLinejoin="round"
          />
          <Path
            d="M100 212 C104 150 112 118 128 112 C146 108 162 120 173 129 C181 136 177 146 167 146 C157 146 150 151 145 159 C141 166 140 180 140 212 Z"
            fill={c.face}
          />
          {/* Closed, sleepy eye. */}
          <Path d="M138 123 Q144 129 150 123" fill="none" stroke={c.ink} strokeWidth={3.4} strokeLinecap="round" />
          <Ellipse cx={148} cy={136} rx={6} ry={4} fill={c.cheek} opacity={0.55} />
          <Circle cx={175} cy={137} r={6} fill={c.ink} />
        </G>
        {/* Blanket, and its fold running to the bottom edge. */}
        <Path d="M250 116 C222 118 204 130 186 139 C162 151 100 138 0 150 L0 200 L250 200 Z" fill={c.blanket} />
        <Path
          d="M240 128 C212 134 192 150 178 164 C172 170 168 176 166 182 L157 182 C161 170 169 160 180 151 C198 138 216 130 240 128 Z"
          fill={c.fold}
        />
        <Path d="M192 34 Q192 48 206 48 Q192 48 192 62 Q192 48 178 48 Q192 48 192 34 Z" fill={c.sparkle} />
        <Path d="M214 64 Q214 71 221 71 Q214 71 214 78 Q214 71 207 71 Q214 71 214 64 Z" fill={c.sparkleSmall} />
      </G>
    </Svg>
  );
}
