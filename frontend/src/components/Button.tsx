import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, Text } from 'react-native';
import Animated, {
  ReduceMotion,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

import { DURATION, EASE, PRESS_SCALE, SPRING_PRESS } from '@/constants/motion';
import { useGuardedPress } from '@/hooks/useGuardedPress';
import { useTheme } from '@/hooks/useTheme';

/** Shrinks a little while held and springs back on release. Opacity feedback stays under reduced motion. */
function usePressScale() {
  const reduced = useReducedMotion();
  const scale = useSharedValue(1);
  const style = useAnimatedStyle(() => ({
    transform: [{ scale: scale.get() }],
  }));
  return {
    style,
    onPressIn: () => {
      if (!reduced)
        scale.set(
          withTiming(PRESS_SCALE, {
            duration: DURATION.instant,
            easing: EASE.out,
          }),
        );
    },
    onPressOut: () => {
      scale.set(withSpring(1, { ...SPRING_PRESS, reduceMotion: ReduceMotion.System }));
    },
  };
}

export type ButtonVariant = 'primary' | 'secondary' | 'alert' | 'ghost';

type ButtonProps = {
  title: string;
  /** May return a promise: the button then shows a spinner and ignores taps until it settles. */
  onPress: () => unknown;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  /** Stretch to the parent's width (forms, dialogs). */
  fullWidth?: boolean;
  /** Optional icon before the label. */
  icon?: ReactNode;
};

const FILL: Record<ButtonVariant, string> = {
  primary: 'bg-accent',
  secondary: 'bg-accent/25',
  alert: 'bg-danger',
  ghost: '',
};

const LABEL: Record<ButtonVariant, string> = {
  primary: 'text-on-accent',
  secondary: 'text-ink',
  alert: 'text-on-danger',
  ghost: 'text-accent-text',
};

/**
 * The one button: rounded, 44px tall, sentence-case semibold label. Shows a spinner while `loading`
 * or while an async `onPress` runs, and never runs `onPress` twice at once.
 */
export function Button({
  title,
  onPress,
  variant = 'primary',
  loading = false,
  disabled = false,
  fullWidth = false,
  icon,
}: ButtonProps) {
  const { colors } = useTheme();
  const press = usePressScale();
  const guarded = useGuardedPress(onPress);
  const busy = loading || guarded.pending;
  const inactive = busy || disabled;
  const spinner = {
    primary: colors['on-accent'],
    secondary: colors.ink,
    alert: colors['on-danger'],
    ghost: colors['accent-text'],
  }[variant];
  return (
    <Animated.View style={[fullWidth ? { alignSelf: 'stretch' } : null, press.style]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: inactive, busy }}
        disabled={inactive}
        onPress={guarded.press}
        onPressIn={press.onPressIn}
        onPressOut={press.onPressOut}
        className={`h-11 flex-row items-center justify-center gap-2 rounded-xl px-6 active:opacity-80 ${FILL[variant]} ${
          disabled ? 'opacity-40' : ''
        }`}
      >
        {busy ? (
          <ActivityIndicator color={spinner} />
        ) : (
          <>
            {icon}
            <Text className={`font-sans-semibold text-base ${LABEL[variant]}`}>{title}</Text>
          </>
        )}
      </Pressable>
    </Animated.View>
  );
}

type IconButtonProps = {
  /** Read out by screen readers, since the button has no visible label. */
  label: string;
  onPress: () => unknown;
  children: ReactNode;
};

/** Round 44px button for a single icon. */
export function IconButton({ label, onPress, children }: IconButtonProps) {
  const press = usePressScale();
  const guarded = useGuardedPress(onPress);
  return (
    <Animated.View style={press.style}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ busy: guarded.pending }}
        disabled={guarded.pending}
        onPress={guarded.press}
        onPressIn={press.onPressIn}
        onPressOut={press.onPressOut}
        className="size-11 items-center justify-center rounded-full bg-surface active:opacity-80"
      >
        {children}
      </Pressable>
    </Animated.View>
  );
}
