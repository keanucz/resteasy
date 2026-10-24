import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from '@/components/AppText';
import { LoginForm } from '@/components/LoginForm';
import { Logo } from '@/components/Logo';
import { SkyBackdrop } from '@/components/SkyHeader';
import { APP_NAME, TAGLINE } from '@/constants/brand';
import { RING, SKY_DETAIL } from '@/constants/sky';
import { useTheme } from '@/hooks/useTheme';

/** px from below the status bar to the bottom of the sky's arc; just clears the logo, name and tagline. */
const LOGIN_HORIZON = 290;

/** Landing route for signed-out users: the asleep sky with the brand, then the form under its arc. */
export default function LoginScreen() {
  const insets = useSafeAreaInsets();
  const { scheme } = useTheme();
  return (
    <KeyboardAvoidingView className="flex-1 bg-canvas" behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView
        className="flex-1"
        contentContainerStyle={{ flexGrow: 1, paddingBottom: insets.bottom + 24 }}
        keyboardShouldPersistTaps="handled"
      >
        <SkyBackdrop state="asleep" horizon={LOGIN_HORIZON}>
          <View className="items-center gap-4 px-6 pt-12">
            {/* The badge's navy is the sky's own, so the photo ring's hairline sets it apart. */}
            <Logo size={128} outline={RING.neutral[scheme]} />
            <View className="items-center gap-1.5">
              <AppText variant="title" accessibilityRole="header">
                {APP_NAME}
              </AppText>
              <Text className="font-display-regular text-lg" style={{ color: SKY_DETAIL[scheme] }}>
                {TAGLINE}
              </Text>
            </View>
          </View>
        </SkyBackdrop>
        {/* Pulled up into the sky's fade, so the fields sit near the middle of the screen. */}
        <View className="-mt-6 items-center px-6">
          <LoginForm />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
