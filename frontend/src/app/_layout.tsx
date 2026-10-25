import '../../global.css';

import {
  Figtree_400Regular,
  Figtree_500Medium,
  Figtree_600SemiBold,
  Figtree_700Bold,
} from '@expo-google-fonts/figtree';
import { Literata_400Regular, Literata_600SemiBold, Literata_600SemiBold_Italic } from '@expo-google-fonts/literata';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { colorScheme } from 'nativewind';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { ThemeBubbleProvider } from '@/components/ThemeBubble';
import { ThemeRoot } from '@/components/ThemeRoot';
import { PillowProvider } from '@/hooks/usePillow';
import { PillowLinkProvider, usePillowLink } from '@/hooks/usePillowLink';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';

// The app is night-first, so it opens in dark mode whatever the device uses; light mode is a
// choice made in the app. Skipped during web's static render, where there is no window.
if (typeof window !== 'undefined') {
  colorScheme.set('dark');
}

/**
 * Root layout: loads the fonts and theme, then routes by where the user is: signed out goes to
 * "/login", signed in without a pillow to "/connect", and with a pillow to the tabs.
 */
export default function RootLayout() {
  const { session, loading } = useSession();
  const { scheme } = useTheme();
  const [fontsLoaded, fontError] = useFonts({
    Figtree_400Regular,
    Figtree_500Medium,
    Figtree_600SemiBold,
    Figtree_700Bold,
    Literata_400Regular,
    Literata_600SemiBold,
    Literata_600SemiBold_Italic,
  });

  // On a font error, render anyway with system fonts rather than a blank app.
  if (loading || (!fontsLoaded && !fontError)) {
    return null;
  }

  return (
    // Drag gestures (moving a reminder on the calendar) need the gesture root around everything.
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ThemeRoot>
        <ThemeBubbleProvider>
          <PillowLinkProvider userId={session?.user.id ?? null}>
            <Routes signedIn={session !== null} />
          </PillowLinkProvider>
        </ThemeBubbleProvider>
        <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      </ThemeRoot>
    </GestureHandlerRootView>
  );
}

/** The screens each kind of user may reach; Expo Router redirects to the first allowed one. */
function Routes({ signedIn }: { signedIn: boolean }) {
  const { colors } = useTheme();
  const { pillowId, ready } = usePillowLink();
  // Until /me answers, a signed-in login without a saved link may still have a pillow: wait for it
  // rather than flash the pairing screen.
  if (signedIn && pillowId === null && !ready) return null;
  return (
    // One read of the pillow's data, shared by Tonight, Settings and the night screen.
    <PillowProvider pillowId={signedIn ? pillowId : null}>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas } }}>
        <Stack.Protected guard={signedIn && pillowId !== null}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="night/[start]" />
        </Stack.Protected>
        <Stack.Protected guard={signedIn && pillowId === null}>
          <Stack.Screen name="connect" />
        </Stack.Protected>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="login" />
        </Stack.Protected>
        {/* Every component in both schemes; open /styleguide while building screens. */}
        <Stack.Screen name="styleguide" />
      </Stack>
    </PillowProvider>
  );
}
