import { useMemo, useState } from 'react';
import { View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { useTheme } from '@/hooks/useTheme';

const HEIGHT = 56;

/**
 * Each ridge as its turning points, left to right: x as a fraction of the width, y as px above the
 * bottom. Peaks and dips alternate, so the line rolls instead of zigzagging.
 */
const BACK: [number, number][] = [
  [0, 22],
  [0.1, 34],
  [0.22, 18],
  [0.36, 42],
  [0.5, 20],
  [0.63, 32],
  [0.76, 16],
  [0.9, 38],
  [1, 26],
];
const FRONT: [number, number][] = [
  [0, 10],
  [0.16, 22],
  [0.3, 8],
  [0.47, 18],
  [0.6, 6],
  [0.78, 24],
  [0.92, 10],
  [1, 14],
];

/** A ridge through its turning points, flat at each one, closed along the bottom. */
function ridge(points: [number, number][], width: number) {
  const at = points.map(([fx, up]) => [fx * width, HEIGHT - up] as const);
  let d = `M0,${HEIGHT} L${at[0][0].toFixed(1)},${at[0][1].toFixed(1)}`;
  for (let i = 1; i < at.length; i++) {
    const [x0, y0] = at[i - 1];
    const [x1, y1] = at[i];
    const mid = (x0 + x1) / 2;
    d += ` C${mid.toFixed(1)},${y0.toFixed(1)} ${mid.toFixed(1)},${y1.toFixed(1)} ${x1.toFixed(1)},${y1.toFixed(1)}`;
  }
  return `${d} L${width},${HEIGHT} Z`;
}

/**
 * Two faint ridges of small hills at the very end of a page, below the last card, so the screen
 * comes to rest on a landscape like the sky it starts with. Decoration only: nothing sits on them.
 */
export function Hills() {
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const shapes = useMemo(() => (width ? { back: ridge(BACK, width), front: ridge(FRONT, width) } : null), [width]);
  return (
    <View
      pointerEvents="none"
      accessible={false}
      importantForAccessibility="no-hide-descendants"
      style={{ height: HEIGHT }}
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
    >
      {shapes ? (
        <Svg width={width} height={HEIGHT} accessible={false}>
          <Path d={shapes.back} fill={colors.surface} opacity={0.7} />
          <Path d={shapes.front} fill={colors.hairline} opacity={0.45} />
        </Svg>
      ) : null}
    </View>
  );
}
