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

import { ThemeRoot } from '@/components/ThemeRoot';
import { useSession } from '@/hooks/useSession';
import { useTheme } from '@/hooks/useTheme';

// The app is night-first, so it opens in dark mode whatever the device uses; light mode is a
// choice made in the app. Skipped during web's static render, where there is no window.
if (typeof window !== 'undefined') {
  colorScheme.set('dark');
}

/** Root layout: loads the fonts and theme, then sends signed-in users to "/" and everyone else to "/login". */
export default function RootLayout() {
  const { session, loading } = useSession();
  const { scheme, colors } = useTheme();
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
    <ThemeRoot>
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.canvas } }}>
        <Stack.Protected guard={session !== null}>
          <Stack.Screen name="index" />
        </Stack.Protected>
        <Stack.Protected guard={session === null}>
          <Stack.Screen name="login" />
        </Stack.Protected>
        {/* Every component in both schemes; open /styleguide while building screens. */}
        <Stack.Screen name="styleguide" />
      </Stack>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
    </ThemeRoot>
  );
}
