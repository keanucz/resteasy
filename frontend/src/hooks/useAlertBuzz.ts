import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { AppState, Vibration } from 'react-native';

import { ALERT_BUZZ_EVERY_MS, ALERT_BUZZ_MS } from '@/constants/pillow';

/** One strong haptic, then a buzz every ALERT_BUZZ_EVERY_MS until the returned stop is called. */
function startBuzz(): () => void {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {
    // No haptics engine (web, some Android phones): the vibration below still runs.
  });
  const buzz = () => Vibration.vibrate(ALERT_BUZZ_MS);
  buzz();
  const timer = setInterval(buzz, ALERT_BUZZ_EVERY_MS);
  return () => {
    clearInterval(timer);
    Vibration.cancel();
  };
}

/** One gentle "it's over" haptic, when an alert ends well. */
export function tapAllClear() {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {
    // No haptics engine: the card on Tonight says it anyway.
  });
}

/** Buzz like an alert for `ms`, for the test button in Settings. */
export function buzzFor(ms: number) {
  const stop = startBuzz();
  setTimeout(stop, ms);
}

/** While `active` and the app is open, the phone keeps buzzing; it stops the moment `active` turns false. */
export function useAlertBuzz(active: boolean) {
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => setForeground(s === 'active'));
    return () => sub.remove();
  }, []);
  useEffect(() => (active && foreground ? startBuzz() : undefined), [active, foreground]);
}
