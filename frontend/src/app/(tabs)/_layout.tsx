import { Tabs } from 'expo-router/tabs';
import { Platform } from 'react-native';

import { CalendarIcon, MoonIcon, SlidersIcon } from '@/components/TabIcons';
import { fonts } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';

/** The tab bar's height on the web, where no safe area pads it. */
const WEB_TAB_BAR_H = 58;

/** Three sections once a pillow is connected: Tonight (the night so far), Reminders and Settings. */
export default function TabsLayout() {
  const { colors } = useTheme();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.canvas },
        tabBarActiveTintColor: colors['accent-text'],
        tabBarInactiveTintColor: colors['ink-muted'],
        // On the web the bar has no safe area to grow into, so it gets room for the label's descenders
        // (the g in "Settings"); on phones the navigator sizes it with the safe area.
        tabBarStyle: {
          backgroundColor: colors.canvas,
          borderTopColor: colors.hairline,
          ...(Platform.OS === 'web' ? { height: WEB_TAB_BAR_H, paddingBottom: 6 } : null),
        },
        tabBarLabelStyle: { fontFamily: fonts.sansSemibold, fontSize: 11, lineHeight: 15 },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Tonight', tabBarIcon: ({ color }) => <MoonIcon color={color} /> }} />
      <Tabs.Screen
        name="reminders"
        options={{ title: 'Reminders', tabBarIcon: ({ color }) => <CalendarIcon color={color} /> }}
      />
      <Tabs.Screen
        name="settings"
        options={{ title: 'Settings', tabBarIcon: ({ color }) => <SlidersIcon color={color} /> }}
      />
    </Tabs>
  );
}
