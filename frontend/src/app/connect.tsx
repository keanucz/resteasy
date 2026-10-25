import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import Animated, { FadeIn, ReduceMotion } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Logo } from '@/components/Logo';
import { SkyBackdrop } from '@/components/SkyHeader';
import { CONNECT_FAILED, CONNECT_STEPS } from '@/constants/pillow';
import { DURATION, EASE } from '@/constants/motion';
import { RING, SKY_DETAIL } from '@/constants/sky';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useTheme } from '@/hooks/useTheme';
import { signOut } from '@/services/auth';

/** px from below the status bar to the bottom of the sky's arc, as on the login screen. */
const CONNECT_HORIZON = 290;

/**
 * First stop after signing in: one button that pairs the pillow. While it works, each step is said
 * in words (never a bare spinner); once linked, the app moves on to Tonight by itself.
 */
export default function ConnectScreen() {
  const insets = useSafeAreaInsets();
  const { scheme, colors } = useTheme();
  const { connect, people, refreshAccount } = usePillowLink();
  const [step, setStep] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pair = async () => {
    setError(null);
    // A login that looks after nobody yet names the person first; the pillow is set up for them there.
    // /me is read again first, so a backend that couldn't be reached never passes for a new login.
    if (people.length === 0) {
      const account = await refreshAccount();
      if (!account) {
        setError(CONNECT_FAILED);
        return;
      }
      if (account.people.length === 0) {
        router.push('/connect-name');
        return;
      }
    }
    // Awaited, so the button stays busy for the whole pairing, not just the /me read.
    try {
      await connect(setStep);
    } catch (e) {
      setStep(null);
      setError(e instanceof Error ? e.message : CONNECT_FAILED);
    }
  };

  return (
    <View className="flex-1 bg-canvas" style={{ paddingBottom: insets.bottom + 24 }}>
      <SkyBackdrop state="asleep" horizon={CONNECT_HORIZON}>
        <View className="items-center gap-4 px-6 pt-12">
          <Logo size={128} outline={RING.neutral[scheme]} />
          <View className="items-center gap-1.5">
            <AppText variant="title" accessibilityRole="header">
              Connect the pillow
            </AppText>
            <Text className="text-center font-display-regular text-lg" style={{ color: SKY_DETAIL[scheme] }}>
              Plug it in by the bed and keep your phone nearby.
            </Text>
          </View>
        </View>
      </SkyBackdrop>
      <View className="-mt-6 flex-1 items-center px-6">
        <View className="w-full max-w-sm gap-4">
          <Text className="font-sans text-base leading-6 text-ink-muted">
            {"The pillow senses lying down and getting up, and talks to them if they don't come back to bed. " +
              "There's no camera. Tell them it's there before the first night."}
          </Text>
          {/* The step line is reserved, so the button never jumps when pairing starts. */}
          <View className="min-h-6 flex-row items-center gap-2.5" accessibilityLiveRegion="polite">
            {step !== null ? (
              <Animated.View
                key={step}
                entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
                className="flex-row items-center gap-2.5"
              >
                <ActivityIndicator size="small" color={colors['accent-text']} />
                <Text className="font-sans text-base text-ink">{CONNECT_STEPS[step]}</Text>
              </Animated.View>
            ) : error ? (
              <Text className="font-sans text-sm text-danger-text">{error}</Text>
            ) : null}
          </View>
          <View className="gap-1">
            <Button
              fullWidth
              title="Connect pillow"
              loading={step !== null}
              onPress={pair}
            />
            <Button fullWidth variant="ghost" title="Log out" onPress={signOut} disabled={step !== null} />
          </View>
        </View>
      </View>
    </View>
  );
}
