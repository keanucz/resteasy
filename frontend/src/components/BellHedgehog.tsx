import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Path } from 'react-native-svg';

import { Hedgehog } from '@/components/Hedgehog';
import { logoColors } from '@/constants/theme';

/** The bell's box against the hedgehog's width, and where it hangs (in front of the snout). */
const BELL_W = 0.3;
const BELL_LEFT = 0.86;
const BELL_TOP = 0.42;
/** One ring: a few swings either way, each smaller, about a second in all. */
const SWINGS = [16, -12, 8, -4, 0];
const SWING_MS = 170;

/** Box a BellHedgehog of `size` needs, bell included. */
export function bellHedgehogBox(size: number) {
  return { width: size * (BELL_LEFT + BELL_W), height: (size * 38) / 56 + size * 0.08 };
}

/**
 * The hedgehog in its nightcap, awake and holding up a little bell: the one who reminds her. Each
 * new `ring` swings the bell (a reminder was just set); under reduced motion it stays still.
 */
export function BellHedgehog({ size = 64, ring = 0 }: { size?: number; ring?: number }) {
  const reduced = useReducedMotion();
  const swing = useSharedValue(0);
  const box = bellHedgehogBox(size);
  const bell = size * BELL_W;

  useEffect(() => {
    if (!ring || reduced) return;
    swing.set(
      withSequence(...SWINGS.map((deg) => withTiming(deg, { duration: SWING_MS, easing: Easing.inOut(Easing.sin) }))),
    );
    return () => cancelAnimation(swing);
  }, [ring, reduced, swing]);

  // Swings from the handle at its top: shift down, rotate, shift back up.
  const style = useAnimatedStyle(() => ({
    transform: [{ translateY: -bell / 2 }, { rotate: `${swing.get()}deg` }, { translateY: bell / 2 }],
  }));

  return (
    <View accessible={false} style={{ width: box.width, height: box.height }}>
      <View style={{ position: 'absolute', left: 0, bottom: 0 }}>
        <Hedgehog size={size} mood="awake" />
      </View>
      <Animated.View
        style={[{ position: 'absolute', left: size * BELL_LEFT, top: size * BELL_TOP * (38 / 56) }, style]}
      >
        <Bell size={bell} />
      </Animated.View>
    </View>
  );
}

/** A small hand bell in the logo's colours: a loop to hold, a dome, a rim and the clapper. */
function Bell({ size }: { size: number }) {
  const spines = logoColors['logo-spines'];
  return (
    <Svg width={size} height={size * 1.1} viewBox="0 0 20 22" accessible={false}>
      <Circle cx={10} cy={3.2} r={2} fill="none" stroke={spines} strokeWidth={1.4} />
      <Path
        d="M3.5 16.5 C3.5 9.5 6 6 10 6 C14 6 16.5 9.5 16.5 16.5 Z"
        fill={logoColors['logo-blanket']}
        stroke={spines}
        strokeWidth={1.2}
        strokeLinejoin="round"
      />
      <Path d="M7 9.5 Q8 8 9.5 7.6" stroke={logoColors['logo-face']} strokeWidth={1.2} strokeLinecap="round" />
      <Path d="M2 17 H18" stroke={spines} strokeWidth={2} strokeLinecap="round" />
      <Circle cx={10} cy={19.4} r={1.8} fill={spines} />
    </Svg>
  );
}
