import { memo, type PropsWithChildren, type ReactNode, useEffect } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Text, View } from 'react-native';
import Animated, {
  Easing,
  FadeIn,
  FadeOut,
  ReduceMotion,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { ThemeRoot } from '@/components/ThemeRoot';
import { DURATION, EASE } from '@/constants/motion';
import { useTheme } from '@/hooks/useTheme';

type NotificationCardProps = {
  initials: string;
  title: string;
  detail?: string;
  time: string;
  /** Escalation: red avatar with "!". */
  alert?: boolean;
  onPress?: () => void;
};

/** In-app notification: face, what happened, when. */
export function NotificationCard({ initials, title, detail, time, alert = false, onPress }: NotificationCardProps) {
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      disabled={!onPress}
      onPress={onPress}
      className="flex-row items-start gap-3 rounded-2xl bg-surface p-3 shadow-lg active:opacity-80"
    >
      <Avatar small initials={alert ? '!' : initials} tone={alert ? 'danger' : 'accent'} />
      <View className="flex-1 gap-0.5">
        <Text className="font-sans-semibold text-sm text-ink">{title}</Text>
        {detail ? <Text className="font-sans text-[13px] text-ink-muted">{detail}</Text> : null}
      </View>
      <Text className="font-sans text-xs text-ink-muted">{time}</Text>
    </Pressable>
  );
}

type DialogCardProps = {
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  cancelLabel?: string;
  onCancel: () => void;
  /** Use the alert button for a destructive or urgent confirm. */
  danger?: boolean;
};

/** Dialog content: title, one sentence, the main action, and a quiet way out under it. */
export function DialogCard({
  title,
  body,
  confirmLabel,
  onConfirm,
  cancelLabel = 'Not now',
  onCancel,
  danger = false,
}: DialogCardProps) {
  return (
    <View className="w-full max-w-sm items-center gap-2.5 rounded-card bg-surface p-[18px]">
      <Text className="text-center font-display text-lg text-ink">{title}</Text>
      <Text className="text-center font-sans text-sm text-ink-muted">{body}</Text>
      <View className="mt-1.5 w-full gap-2">
        <Button fullWidth title={confirmLabel} variant={danger ? 'alert' : 'primary'} onPress={onConfirm} />
        <Button fullWidth title={cancelLabel} variant="ghost" onPress={onCancel} />
      </View>
    </View>
  );
}

type DialogProps = DialogCardProps & { visible: boolean };

/** DialogCard in a modal over a dimmed screen. */
export function Dialog({ visible, ...card }: DialogProps) {
  return (
    <Modal transparent animationType="fade" visible={visible} onRequestClose={card.onCancel}>
      {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
      <ThemeRoot>
        <View className="flex-1 items-center justify-center bg-black/50 p-6">
          <DialogCard {...card} />
        </View>
      </ThemeRoot>
    </Modal>
  );
}

type SheetProps = PropsWithChildren<{
  visible: boolean;
  title: string;
  /** A line under the title. */
  note?: ReactNode;
  onClose: () => void;
  /** Pinned under the scrolling content: the sheet's main action. */
  footer?: ReactNode;
}>;

/**
 * A sheet rising from the bottom over a dimmed screen, for a task with a few steps (add a
 * reminder). Its content scrolls; `footer` stays in reach of the thumb. A tap above it closes it.
 */
export function Sheet({ visible, title, note, onClose, footer, children }: SheetProps) {
  const insets = useSafeAreaInsets();
  return (
    <Modal transparent animationType="slide" visible={visible} onRequestClose={onClose}>
      {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
      <ThemeRoot>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} className="flex-1">
          <View className="flex-1 justify-end bg-black/50">
            <Pressable accessibilityLabel="Close" onPress={onClose} className="min-h-12 flex-1" />
            <View className="max-h-[92%] rounded-t-card bg-canvas" style={{ paddingBottom: insets.bottom }}>
              <View className="flex-row items-start gap-3 px-4 pb-2 pt-5">
                <View className="flex-1 gap-1">
                  <Text accessibilityRole="header" className="font-display text-xl text-ink">
                    {title}
                  </Text>
                  {note ? <Text className="font-sans text-sm text-ink-muted">{note}</Text> : null}
                </View>
                <Button variant="ghost" title="Close" onPress={onClose} />
              </View>
              <ScrollView
                contentContainerClassName="gap-6 px-4 pb-6 pt-2"
                keyboardShouldPersistTaps="handled"
                keyboardDismissMode="on-drag"
              >
                {children}
              </ScrollView>
              {footer ? <View className="gap-2 border-t border-hairline px-4 pb-3 pt-3">{footer}</View> : null}
            </View>
          </View>
        </KeyboardAvoidingView>
      </ThemeRoot>
    </Modal>
  );
}

type UndoToastProps = {
  message: string;
  detail?: string;
  /** How long until the change is sent; a hairline under the text runs down over it. */
  duration: number;
  onUndo: () => void;
};

/**
 * What just changed, with Undo, floating over the bottom of the screen. The change is only sent
 * once the line under it runs out, so Undo leaves nothing behind. Under reduced motion the line
 * stays still.
 */
export function UndoToast({ message, detail, duration, onUndo }: UndoToastProps) {
  const { colors } = useTheme();
  const reduced = useReducedMotion();
  const left = useSharedValue(1);
  useEffect(() => {
    left.set(1);
    if (!reduced) left.set(withTiming(0, { duration, easing: Easing.linear }));
  }, [message, duration, reduced, left]);
  const line = useAnimatedStyle(() => ({ transform: [{ scaleX: left.get() }] }));
  return (
    <Animated.View
      entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
      exiting={FadeOut.duration(DURATION.exit).easing(EASE.in).reduceMotion(ReduceMotion.System)}
    >
      <View className="overflow-hidden rounded-2xl bg-surface shadow-lg">
        <View className="flex-row items-center gap-2 py-2 pl-4 pr-1.5">
          <View className="flex-1 gap-0.5" accessibilityLiveRegion="polite">
            <Text className="font-sans-semibold text-sm text-ink">{message}</Text>
            {detail ? <Text className="font-sans text-[13px] text-ink-muted">{detail}</Text> : null}
          </View>
          <Button variant="ghost" title="Undo" onPress={onUndo} />
        </View>
        <Animated.View
          style={[{ height: 2, backgroundColor: colors.accent, opacity: 0.6, transformOrigin: 'left' }, line]}
        />
      </View>
    </Animated.View>
  );
}

/** A plain note floating over the bottom of the screen: what a drag will do, or why a change failed. */
export function Toast({ message, detail, action }: { message: string; detail?: string; action?: ReactNode }) {
  return (
    <Animated.View
      entering={FadeIn.duration(DURATION.fast).easing(EASE.out).reduceMotion(ReduceMotion.System)}
      exiting={FadeOut.duration(DURATION.exit).easing(EASE.in).reduceMotion(ReduceMotion.System)}
    >
      <View className="flex-row items-center gap-2 rounded-2xl bg-surface py-3 pl-4 pr-1.5 shadow-lg">
        <View className="min-h-11 flex-1 justify-center gap-0.5" accessibilityLiveRegion="polite">
          <Text className="font-sans-semibold text-sm text-ink">{message}</Text>
          {detail ? <Text className="font-sans text-[13px] text-ink-muted">{detail}</Text> : null}
        </View>
        {action}
      </View>
    </Animated.View>
  );
}

/** The result of a save or an action, shown next to its control. */
export type Status = { kind: 'saved' | 'error'; text: string };

/** A line that is always there, so "Saved" or a save error appears without moving anything. */
export const StatusLine = memo(function StatusLine({ status }: { status: Status | null }) {
  return (
    <View className="-mt-1 min-h-5 justify-center">
      {status ? (
        <Animated.View
          key={`${status.kind}:${status.text}`}
          entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
          exiting={FadeOut.duration(DURATION.exit).easing(EASE.in).reduceMotion(ReduceMotion.System)}
        >
          <Text
            accessibilityLiveRegion="polite"
            className={`font-sans text-sm ${status.kind === 'error' ? 'text-danger-text' : 'text-ink-muted'}`}
          >
            {status.text}
          </Text>
        </Animated.View>
      ) : null}
    </View>
  );
});
