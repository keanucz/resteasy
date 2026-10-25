import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

/** Root layout: navigation stack and status bar shared by every route. */
export default function RootLayout() {
  return (
    <>
      <Stack screenOptions={{ headerShown: false }} />
      <StatusBar style="auto" />
    </>
  );
}
