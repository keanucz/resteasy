import { createContext, type PropsWithChildren, useContext, useEffect } from 'react';
import { type DimensionValue, View } from 'react-native';
import Animated, {
  Easing,
  ReduceMotion,
  type SharedValue,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { SKELETON_DIM, SKELETON_HALF_CYCLE } from '@/constants/motion';
import { useTheme } from '@/hooks/useTheme';

/** One shared breath per group, so every bone on screen pulses in sync. */
const PulseContext = createContext<SharedValue<number> | null>(null);

/**
 * Wraps a loading area: announces it as busy and drives one slow pulse for all its bones. A dim
 * pulse rather than a shimmer, because a bright sweep is a moving light in a dark bedroom.
 */
export function SkeletonGroup({ children }: PropsWithChildren) {
  const reduced = useReducedMotion();
  const pulse = useSharedValue(1);
  useEffect(() => {
    if (reduced) return;
    pulse.set(
      withRepeat(
        withTiming(SKELETON_DIM, {
          duration: SKELETON_HALF_CYCLE,
          easing: Easing.inOut(Easing.sin),
          reduceMotion: ReduceMotion.System,
        }),
        -1,
        true,
      ),
    );
  }, [pulse, reduced]);
  return (
    <PulseContext.Provider value={pulse}>
      <View accessibilityRole="progressbar" accessibilityLabel="Loading" accessibilityState={{ busy: true }}>
        <View importantForAccessibility="no-hide-descendants">{children}</View>
      </View>
    </PulseContext.Provider>
  );
}

type BoneProps = {
  width: DimensionValue;
  height: number;
  /** Avatars and the photo ring. */
  round?: boolean;
};

/** One placeholder shape, sized like the text or image it stands in for. Use inside a SkeletonGroup. */
export function Bone({ width, height, round = false }: BoneProps) {
  const { colors } = useTheme();
  const pulse = useContext(PulseContext);
  const style = useAnimatedStyle(() => ({ opacity: pulse ? pulse.get() : 1 }));
  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius: round ? 999 : 6,
          backgroundColor: colors.bone,
        },
        style,
      ]}
    />
  );
}

/** Stands in for a StatTile: same shell, label and value bones. */
export function StatTileSkeleton() {
  return (
    <View className="flex-1 gap-2 rounded-2xl bg-surface p-3.5">
      <Bone width="40%" height={12} />
      <Bone width="60%" height={20} />
    </View>
  );
}

/** Stands in for a ListRow with an avatar: same shell, no bone for the trailing control. */
export function ListRowSkeleton() {
  return (
    <View className="flex-row items-center gap-3 rounded-2xl bg-surface px-3.5 py-3.5">
      <Bone width={44} height={44} round />
      <View className="flex-1 gap-1.5">
        <Bone width="45%" height={16} />
        <Bone width="30%" height={13} />
      </View>
    </View>
  );
}

/** Stands in for a SummaryCard: a heading and three lines of body. */
export function SummaryCardSkeleton() {
  return (
    <View className="gap-3 rounded-2xl bg-surface p-3.5">
      <Bone width="55%" height={20} />
      <View className="gap-2">
        <Bone width="100%" height={14} />
        <Bone width="92%" height={14} />
        <Bone width="60%" height={14} />
      </View>
    </View>
  );
}
