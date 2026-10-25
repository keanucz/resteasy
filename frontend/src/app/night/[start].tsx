import { router, useLocalSearchParams } from 'expo-router';
import { useMemo } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';

import { IconButton } from '@/components/Button';
import { Card } from '@/components/Card';
import { MovementChart, nightWindow, NightShareChart, TemperatureChart } from '@/components/Charts';
import { NightHeading } from '@/components/NightHeading';
import { NightRibbon } from '@/components/NightRibbon';
import { SkeletonGroup, StatTileSkeleton, SummaryCardSkeleton } from '@/components/Skeleton';
import { DataTable, StatTile, SummaryCard } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { MONTH_NIGHTS } from '@/constants/pillow';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useNow, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useReadings } from '@/hooks/useReadings';
import { useTheme } from '@/hooks/useTheme';
import {
  clockTime,
  nightAt,
  nightDate,
  nightStats,
  nightTimeline,
  nightTitle,
  ribbonNow,
  ribbonSegments,
  summariseNight,
} from '@/services/night';
import { nightClimate, signedDegrees } from '@/services/readings';

/** An hour before the ribbon starts, so the chart's first point has the room as she went to bed. */
const LEAD_IN_MS = 60 * 60 * 1000;

/**
 * One night in full, opened from the week: what happened in a sentence, the ribbon, the numbers,
 * the bedroom's temperature, how much the pillow moved, how the night was spent and every event.
 */
export default function NightScreen() {
  const { start } = useLocalSearchParams<{ start: string }>();
  const { pillowId } = usePillowLink();
  const pillow = usePillow();
  const now = useNow();
  const insets = useSafeAreaInsets();
  const showSkeleton = useDelayedLoading(pillow.loading);
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';
  const name = pillow.resident?.preferred_name ?? 'Mum';

  const night = nightAt(Number(start), now, tz, MONTH_NIGHTS);
  const window = useMemo(() => nightWindow(night?.ribbonStart ?? 0), [night?.ribbonStart]);
  const readings = useReadings(
    night ? pillowId : null,
    window.start - LEAD_IN_MS,
    window.end,
    Boolean(night && !night.over),
  );

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
  const summary = summariseNight(pillow.events, pillow.incidents, night, title, name);
  const segments = ribbonSegments(pillow.events, night, now);
  const stats = nightStats(pillow.events, night, now);
  const climate = nightClimate(readings.rows);
  const timeline = nightTimeline(pillow.events, night, tz);

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

      {showSkeleton ? (
        <SkeletonGroup>
          <View className="gap-2.5">
            <SummaryCardSkeleton />
            <View className="flex-row gap-2.5">
              <StatTileSkeleton />
              <StatTileSkeleton />
            </View>
          </View>
        </SkeletonGroup>
      ) : (
        <View className="gap-2.5">
          <SummaryCard heading={<NightHeading tone={summary.tone} soFar={!night.over} />} body={summary.line} />
          <Card>
            <NightRibbon segments={segments} now={ribbonNow(night, now)} />
          </Card>
          <View className="flex-row gap-2.5">
            <StatTile label={stats.asleepLabel} value={stats.asleepValue} />
            <StatTile label="Out of bed" value={stats.tripsValue} />
          </View>
          <View className="flex-row gap-2.5">
            <StatTile
              label="Bedroom change"
              value={climate ? signedDegrees(climate.end - climate.start) : '–'}
              detail={climate ? `${climate.start.toFixed(1)} to ${climate.end.toFixed(1)}°C` : undefined}
            />
            <StatTile
              label="Coldest"
              value={climate ? `${climate.coldest.v.toFixed(1)}°C` : '–'}
              detail={climate ? `at ${clockTime(climate.coldest.t, tz)}` : undefined}
            />
          </View>
        </View>
      )}

      <View className="gap-2.5">
        <TemperatureChart rows={readings.rows} window={window} tz={tz} />
        <MovementChart rows={readings.rows} window={window} tz={tz} />
        <NightShareChart segments={segments} />
      </View>

      <View className="gap-3">
        <Text accessibilityRole="header" className="font-display text-xl text-ink">
          What the pillow noticed
        </Text>
        {timeline.length ? (
          <DataTable
            columns={['Time', 'What happened']}
            rows={timeline.map((e) => [
              e.time,
              e.notable ? (
                <Text key={e.key} className="text-sm">
                  <StatusWord state="up">{e.what}</StatusWord>
                </Text>
              ) : (
                <Text key={e.key} className="font-sans text-sm text-ink">
                  {e.what}
                </Text>
              ),
            ])}
          />
        ) : (
          <Text className="font-sans text-base text-ink-muted">Nothing from the pillow that night.</Text>
        )}
      </View>
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
