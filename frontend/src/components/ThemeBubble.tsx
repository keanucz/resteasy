import { colorScheme } from 'nativewind';
import { createContext, type PropsWithChildren, useCallback, useContext, useRef, useState } from 'react';
import { useWindowDimensions, View } from 'react-native';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { type Scheme, themes } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';

/** The bubble rising from the bottom edge to cover the screen, then the new scheme showing through. */
const RISE_MS = 720;
const REVEAL_MS = 260;
/** Slow start (a small curve peeking up from the bottom), then a smooth sweep to the top. */
const RISE_EASING = Easing.bezier(0.55, 0, 0.25, 1);

type SwitchScheme = (next: Scheme) => void;

const ThemeBubbleContext = createContext<SwitchScheme>((next) => colorScheme.set(next));

/**
 * Changes between light and dark with a bubble of the new canvas colour that grows from the middle
 * of the bottom edge until it fills the screen. The scheme flips underneath it once it is covered,
 * then the bubble fades to show the new look. Under reduced motion the scheme just changes.
 */
export function ThemeBubbleProvider({ children }: PropsWithChildren) {
  const { scheme } = useTheme();
  const { width, height } = useWindowDimensions();
  const reduced = useReducedMotion();
  const grow = useSharedValue(0);
  const fade = useSharedValue(0);
  const [color, setColor] = useState<string | null>(null);
  const busy = useRef(false);

  // Big enough, centred on the bottom edge, to reach the top corners.
  const radius = Math.ceil(Math.sqrt((width / 2) ** 2 + height ** 2)) + 2;

  const finish = useCallback((next: Scheme) => {
    colorScheme.set(next);
  }, []);

  const done = useCallback(() => {
    busy.current = false;
    setColor(null);
  }, []);

  const switchScheme = useCallback<SwitchScheme>(
    (next) => {
      if (next === scheme || busy.current) return;
      if (reduced) {
        colorScheme.set(next);
        return;
      }
      busy.current = true;
      setColor(themes[next].canvas);
      fade.set(1);
      grow.set(0);
      grow.set(
        withTiming(1, { duration: RISE_MS, easing: RISE_EASING }, (finished) => {
          if (!finished) return;
          runOnJS(finish)(next);
          // A frame for the new scheme to paint under the bubble, then let it show through.
          fade.set(
            withTiming(0, { duration: REVEAL_MS, easing: Easing.out(Easing.quad) }, (shown) => {
              if (shown) runOnJS(done)();
            }),
          );
        }),
      );
    },
    [scheme, reduced, fade, grow, finish, done],
  );

  const bubble = useAnimatedStyle(() => ({
    opacity: fade.get(),
    transform: [{ scale: grow.get() }],
  }));

  return (
    <ThemeBubbleContext.Provider value={switchScheme}>
      <View style={{ flex: 1 }}>
        {children}
        {color ? (
          <Animated.View
            pointerEvents="none"
            style={[
              {
                position: 'absolute',
                width: radius * 2,
                height: radius * 2,
                left: width / 2 - radius,
                top: height - radius,
                borderRadius: radius,
                backgroundColor: color,
              },
              bubble,
            ]}
          />
        ) : null}
      </View>
    </ThemeBubbleContext.Provider>
  );
}

/** Switch light and dark with the bubble. */
export function useSwitchScheme(): SwitchScheme {
  return useContext(ThemeBubbleContext);
}
