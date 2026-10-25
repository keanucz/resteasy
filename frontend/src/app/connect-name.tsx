import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import Animated, { FadeIn, ReduceMotion } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { Button } from '@/components/Button';
import { Logo } from '@/components/Logo';
import { SkyBackdrop } from '@/components/SkyHeader';
import { TextField } from '@/components/TextField';
import { DURATION, EASE } from '@/constants/motion';
import { CONNECT_FAILED, CONNECT_STEPS, RESIDENT_NAME_MAX } from '@/constants/pillow';
import { RING, SKY_DETAIL } from '@/constants/sky';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useTheme } from '@/hooks/useTheme';

/** px from below the status bar to the bottom of the sky's arc, as on the connect screen. */
const NAME_HORIZON = 290;

/**
 * After "Connect pillow" on a login that looks after nobody yet: who the pillow is for. Sending the
 * name sets the pillow up for them (a new, empty household with this login as its owner), then
 * pings it; once both boards answer, the app moves on to Tonight by itself.
 */
export default function ConnectNameScreen() {
  const insets = useSafeAreaInsets();
  const { scheme, colors } = useTheme();
  const { connect } = usePillowLink();
  const [name, setName] = useState('');
  const [step, setStep] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = step !== null;
  const trimmed = name.trim();

  // Awaited, so the button and the return key both wait for the whole pairing; a second tap joins
  // the pairing already running rather than setting the pillow up twice.
  const submit = async () => {
    if (!trimmed || busy) return;
    setError(null);
    try {
      await connect(setStep, trimmed);
    } catch (e) {
      setStep(null);
      setError(e instanceof Error ? e.message : CONNECT_FAILED);
    }
  };

  return (
    <KeyboardAvoidingView className="flex-1 bg-canvas" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ flexGrow: 1, paddingBottom: insets.bottom + 24 }}
        keyboardShouldPersistTaps="handled"
      >
        <SkyBackdrop state="asleep" horizon={NAME_HORIZON}>
          <View className="items-center gap-4 px-6 pt-12">
            <Logo size={128} outline={RING.neutral[scheme]} />
            <View className="items-center gap-1.5">
              <AppText variant="title" accessibilityRole="header">
                Who is the pillow for?
              </AppText>
              <Text className="text-center font-display-regular text-lg" style={{ color: SKY_DETAIL[scheme] }}>
                The pillow greets them by this name.
              </Text>
            </View>
          </View>
        </SkyBackdrop>
        <View className="-mt-6 flex-1 items-center px-6">
          <View className="w-full max-w-sm gap-4">
            <TextField
              label="What you call them"
              placeholder="Like Halina"
              value={name}
              onChangeText={setName}
              maxLength={RESIDENT_NAME_MAX}
              autoCapitalize="words"
              autoComplete="off"
              autoCorrect={false}
              returnKeyType="done"
              onSubmitEditing={submit}
              editable={!busy}
            />
            {/* Room for a step or a three-line error is reserved, so the buttons never jump. */}
            <View className="min-h-[72px] justify-center" accessibilityLiveRegion="polite">
              {busy ? (
                <Animated.View
                  key={step}
                  entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
                  className="flex-row items-center gap-2.5"
                >
                  <ActivityIndicator size="small" color={colors['accent-text']} />
                  <Text className="font-sans text-base text-ink">{CONNECT_STEPS[step]}</Text>
                </Animated.View>
              ) : error ? (
                <Text className="font-sans text-base leading-6 text-danger-text" accessibilityRole="alert">
                  {error}
                </Text>
              ) : null}
            </View>
            <View className="gap-1">
              <Button
                fullWidth
                title={trimmed ? `Connect ${trimmed}'s pillow` : 'Connect pillow'}
                loading={busy}
                disabled={!trimmed}
                onPress={submit}
              />
              <Button
                fullWidth
                variant="ghost"
                title="Back"
                disabled={busy}
                onPress={() => (router.canGoBack() ? router.back() : router.replace('/connect'))}
              />
            </View>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
