import { useState } from 'react';
import { Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut, ReduceMotion } from 'react-native-reanimated';

import { Button } from '@/components/Button';
import { TextField } from '@/components/TextField';
import { MIN_PASSWORD_LENGTH } from '@/constants/auth';
import { DURATION, EASE } from '@/constants/motion';
import { signIn, signUp } from '@/services/auth';

type Mode = 'login' | 'signup';

/** What each mode calls its submit button and the quiet link that swaps to the other mode. */
const COPY: Record<Mode, { submit: string; swap: string }> = {
  login: { submit: 'Log in', swap: 'Create an account' },
  signup: { submit: 'Create account', swap: 'I already have an account' },
};

const PASSWORD_HINT = `At least ${MIN_PASSWORD_LENGTH} characters`;

/**
 * Email + password with one primary action. A ghost link under it swaps the form between
 * logging in and creating an account. On failure it clears the password and shows one message;
 * on success the session change routes the user on.
 */
export function LoginForm() {
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async () => {
    setPending(true);
    setError(null);
    const result = await (mode === 'login' ? signIn : signUp)(email, password);
    setPending(false);
    if (!result.ok) {
      setPassword('');
      setError(result.message);
    }
  };

  const swapMode = () => {
    setMode(mode === 'login' ? 'signup' : 'login');
    setError(null);
  };

  const signingUp = mode === 'signup';
  // The line under the password holds the error, or the password rule while creating an account.
  const note = error ?? (signingUp ? PASSWORD_HINT : null);

  return (
    <View className="w-full max-w-sm">
      <View className="gap-4">
        <TextField
          label="Email"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="email"
          textContentType="emailAddress"
          keyboardType="email-address"
          returnKeyType="next"
        />
        <TextField
          label="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete={signingUp ? 'new-password' : 'current-password'}
          textContentType={signingUp ? 'newPassword' : 'password'}
          accessibilityHint={signingUp ? PASSWORD_HINT : undefined}
          returnKeyType="go"
          onSubmitEditing={submit}
        />
      </View>
      {/* The note's line is always reserved, so the buttons never jump when it appears. */}
      <View className="mb-3 mt-1.5 min-h-5 justify-center">
        {note && (
          <Animated.View
            key={note}
            entering={FadeIn.duration(DURATION.base).easing(EASE.out).reduceMotion(ReduceMotion.System)}
            exiting={FadeOut.duration(DURATION.exit).easing(EASE.in).reduceMotion(ReduceMotion.System)}
          >
            <Text
              className={`font-sans text-sm ${error ? 'text-danger-text' : 'text-ink-muted'}`}
              accessibilityLiveRegion="polite"
            >
              {note}
            </Text>
          </Animated.View>
        )}
      </View>
      <View className="gap-1">
        <Button fullWidth title={COPY[mode].submit} onPress={submit} loading={pending} />
        <Button fullWidth variant="ghost" title={COPY[mode].swap} onPress={swapMode} disabled={pending} />
      </View>
    </View>
  );
}
