import { Image, Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { RING } from '@/constants/sky';
import type { PillowState } from '@/constants/status';
import { useTheme } from '@/hooks/useTheme';

type PhotoRingProps = {
  state: PillowState;
  initials: string;
  photoUri?: string;
  size?: number;
};

/**
 * Her photo (or initials) in a thin neutral ring. The ring only speaks when it matters: thick and
 * red when she needs you, dotted when the pillow is offline. The sky and headline carry the rest.
 */
export function PhotoRing({ state, initials, photoUri, size = 64 }: PhotoRingProps) {
  const { scheme } = useTheme();
  const alert = state === 'alert';
  const stroke = alert ? RING.alert[scheme] : RING.neutral[scheme];
  const width = alert ? 3 : state === 'offline' ? 2 : 1.5;
  const inner = size - 12;
  return (
    <View style={{ width: size, height: size }} className="items-center justify-center">
      <Svg width={size} height={size} style={{ position: 'absolute' }}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={(size - width) / 2}
          stroke={stroke}
          strokeWidth={width}
          fill="none"
          strokeDasharray={state === 'offline' ? '0.1 5' : undefined}
          strokeLinecap="round"
        />
      </Svg>
      {photoUri ? (
        <Image source={{ uri: photoUri }} style={{ width: inner, height: inner, borderRadius: inner / 2 }} />
      ) : (
        <View style={{ width: inner, height: inner }} className="items-center justify-center rounded-full bg-surface">
          <Text className={`font-display text-xl ${state === 'offline' ? 'text-ink-muted' : 'text-ink'}`}>{initials}</Text>
        </View>
      )}
    </View>
  );
}
