import { useEffect } from 'react';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Ellipse, G, Path } from 'react-native-svg';

import { logoColors } from '@/constants/theme';

/** The spines: a dome of alternating long and short points, 40 wide, sitting on y = 34. */
const SPINES = (() => {
  const cx = 22;
  const cy = 34;
  const points = 15;
  const steps = Array.from({ length: points * 2 + 1 }, (_, i) => {
    const a = Math.PI - (i / (points * 2)) * Math.PI;
    const r = i % 2 === 0 ? 17 : 22;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy - r * Math.sin(a)).toFixed(1)}`;
  });
  return `M${steps.join(' L')} Z`;
})();

/** One slow breath, in and out, and how much it swells the hedgehog at the top of it. */
const BREATH_MS = 4000;
const BREATH_SWELL = 0.05;

/** How the hedgehog feels: curled up asleep, fidgety and worried, or up and about. */
export type HedgehogMood = 'asleep' | 'restless' | 'awake';

/**
 * The logo's hedgehog on its own, in its nightcap: spines, face and an eye that says its mood. The same `logo-*`
 * colours as the mark, so it reads as the same character in either mode.
 */
export function Hedgehog({
  size = 44,
  mood = 'asleep',
  breathing = false,
}: {
  size?: number;
  mood?: HedgehogMood;
  /** Asleep, it breathes slowly: its back rises and falls while it sits where it is. Still under reduced motion. */
  breathing?: boolean;
}) {
  const ink = logoColors['logo-ink'];
  const spines = logoColors['logo-spines'];
  const height = (size * 38) / 56;
  const reduced = useReducedMotion();
  const breathes = breathing && mood === 'asleep' && !reduced;
  const breath = useSharedValue(0);

  useEffect(() => {
    breath.set(0);
    if (!breathes) return;
    breath.set(withRepeat(withTiming(1, { duration: BREATH_MS / 2, easing: Easing.inOut(Easing.sin) }), -1, true));
    return () => cancelAnimation(breath);
  }, [breathes, breath]);

  const style = useAnimatedStyle(() => {
    const swell = breath.get() * BREATH_SWELL;
    // Scaled about its middle, then shifted up by half the growth, so it swells from where it sits.
    return { transform: [{ translateY: (-height * swell) / 2 }, { scaleY: 1 + swell }, { scaleX: 1 + swell / 4 }] };
  });

  return (
    <Animated.View style={style}>
      <HedgehogArt size={size} height={height} mood={mood} ink={ink} spines={spines} />
    </Animated.View>
  );
}

/** The drawing itself, in the logo's colours. */
function HedgehogArt({
  size,
  height,
  mood,
  ink,
  spines,
}: {
  size: number;
  height: number;
  mood: HedgehogMood;
  ink: string;
  spines: string;
}) {
  return (
    <Svg width={size} height={height} viewBox="0 0 56 38" accessible={false}>
      {mood === 'awake' ? (
        // Up and about: little feet under it.
        <G fill={spines}>
          <Ellipse cx={14} cy={35} rx={3} ry={2.2} />
          <Ellipse cx={36} cy={35} rx={3} ry={2.2} />
        </G>
      ) : null}
      <Path d={SPINES} fill={spines} stroke={spines} strokeWidth={1.5} strokeLinejoin="round" />
      {/* Face: a snout pointing right, tucked against the spines. */}
      <Path
        d="M30 34 C30 24 34 19 40 19 C46 19 51 24 53 28 C55 31 53 33 50 33 L30 34 Z"
        fill={logoColors['logo-face']}
        stroke={spines}
        strokeWidth={1.2}
        strokeLinejoin="round"
      />
      {mood === 'asleep' ? (
        <Path d="M38.5 25.5 Q41 28 43.5 25.5" fill="none" stroke={ink} strokeWidth={1.4} strokeLinecap="round" />
      ) : (
        <Circle cx={41} cy={25.6} r={1.7} fill={ink} />
      )}
      {mood === 'restless' ? (
        <G strokeWidth={1.2} strokeLinecap="round" fill="none">
          {/* A worried brow, and two fidget marks over its back. */}
          <Path d="M38.2 22.4 L43.4 21.2" stroke={ink} />
          <Path d="M8 6 Q6 3 8 0.8" stroke={spines} />
          <Path d="M13 4.5 Q11.4 2 13 0" stroke={spines} />
        </G>
      ) : null}
      <Ellipse cx={42} cy={30} rx={2.4} ry={1.5} fill={logoColors['logo-cheek']} opacity={0.55} />
      <Circle cx={53} cy={29.5} r={1.9} fill={ink} />
      {/* Its nightcap, worn whatever the hour: a floppy cone, a band and a pom-pom. */}
      <Path
        d="M33.5 20 Q31 11 27 6 Q37 8 46 18.6 Z"
        fill={logoColors['logo-blanket']}
        stroke={spines}
        strokeWidth={1}
        strokeLinejoin="round"
      />
      <Path
        d="M33 20.5 Q39.5 17 46.5 19"
        fill="none"
        stroke={logoColors['logo-face']}
        strokeWidth={3}
        strokeLinecap="round"
      />
      <Circle cx={27} cy={6} r={2.6} fill={logoColors['logo-face']} stroke={spines} strokeWidth={0.8} />
    </Svg>
  );
}
