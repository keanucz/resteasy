import { router, useLocalSearchParams } from 'expo-router';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { IconButton } from '@/components/Button';
import { NightDetail } from '@/components/NightDetail';
import { MONTH_NIGHTS } from '@/constants/pillow';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useNow, usePillow } from '@/hooks/usePillow';
import { useTheme } from '@/hooks/useTheme';
import { nightAt, nightDate, nightTitle } from '@/services/night';

/** One night in full, opened from the week: its name and date over the night's detail. */
export default function NightScreen() {
  const { start } = useLocalSearchParams<{ start: string }>();
  const pillow = usePillow();
  const now = useNow();
  const insets = useSafeAreaInsets();
  const showSkeleton = useDelayedLoading(pillow.loading);
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';

  const night = nightAt(Number(start), now, tz, MONTH_NIGHTS);

  if (!night) {
    return (
      <View className="flex-1 gap-4 bg-canvas px-4" style={{ paddingTop: insets.top + 12 }}>
        <BackButton />
        <Text className="font-display text-2xl text-ink">That night is too long ago</Text>
        <Text className="font-sans text-base text-ink-muted">The app keeps the last {MONTH_NIGHTS} nights.</Text>
      </View>
    );
  }

  const title = nightTitle(night, now, tz);

  return (
    <ScrollView
      className="flex-1 bg-canvas"
      contentContainerClassName="gap-8 px-4 pb-12"
      contentContainerStyle={{ paddingTop: insets.top + 12 }}
    >
      <View className="gap-4">
        <BackButton />
        <View className="gap-1">
          <Text accessibilityRole="header" className="font-display text-3xl text-ink">
            {title}
          </Text>
          <Text className="font-sans text-sm text-ink-muted">{nightDate(night, tz)}, 10 pm to 7 am</Text>
        </View>
      </View>
      <NightDetail night={night} title={title} showSkeleton={showSkeleton} />
    </ScrollView>
  );
}

function BackButton() {
  const { colors } = useTheme();
  return (
    <IconButton label="Back" onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}>
      <Svg width={20} height={20} viewBox="0 0 24 24">
        <Path
          d="M15 5 L8 12 L15 19"
          stroke={colors.ink}
          strokeWidth={2}
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
    </IconButton>
  );
}
