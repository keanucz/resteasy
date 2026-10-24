import { Modal, Pressable, Text, View } from 'react-native';

import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { ThemeRoot } from '@/components/ThemeRoot';

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
