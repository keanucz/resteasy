import { memo, useMemo } from 'react';
import { Text, View } from 'react-native';

import { Card } from '@/components/Card';
import { MovementChart, nightWindow, NightShareChart, TemperatureChart } from '@/components/Charts';
import { NightHeading } from '@/components/NightHeading';
import { NightRibbon } from '@/components/NightRibbon';
import { SkeletonGroup, StatTileSkeleton, SummaryCardSkeleton } from '@/components/Skeleton';
import { DataTable, StatTile, SummaryCard } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { useNow, usePillow } from '@/hooks/usePillow';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useReadings } from '@/hooks/useReadings';
import {
  clockTime,
  nightStats,
  nightTimeline,
  type NightWindow,
  ribbonNow,
  ribbonSegments,
  summariseNight,
} from '@/services/night';
import { nightClimate, signedDegrees } from '@/services/readings';

/** An hour before the ribbon starts, so the chart's first point has the room as she went to bed. */
const LEAD_IN_MS = 60 * 60 * 1000;
const TIMELINE_COLUMNS = ['Time', 'What happened'];

/**
 * One night in full: what happened in a sentence, the ribbon, the numbers, the bedroom's
 * temperature, how much the pillow moved, how the night was spent and every event. The night
 * screen shows it for any night; Tonight shows it for the latest one.
 */
export const NightDetail = memo(function NightDetail({
  night,
  title,
  showSkeleton,
}: {
  night: NightWindow;
  /** "Last night", "Tonight" or "Tuesday night", for the summary sentence. */
  title: string;
  showSkeleton: boolean;
}) {
  const { pillowId } = usePillowLink();
  const pillow = usePillow();
  const now = useNow();
  const tz = pillow.resident?.timezone ?? 'America/Los_Angeles';
  const name = pillow.resident?.preferred_name ?? 'Mum';

  const window = useMemo(() => nightWindow(night.ribbonStart), [night.ribbonStart]);
  const readings = useReadings(pillowId, window.start - LEAD_IN_MS, window.end, !night.over);

  const { events, incidents } = pillow;
  const summary = useMemo(
    () => summariseNight(events, incidents, night, title, name),
    [events, incidents, night, title, name],
  );
  // A past night ends at its own end, so only a live one needs working out again as time passes.
  const until = night.over ? night.end : now;
  const segments = useMemo(() => ribbonSegments(events, night, until), [events, night, until]);
  const stats = useMemo(() => nightStats(events, night, until), [events, night, until]);
  const climate = useMemo(() => nightClimate(readings.rows), [readings.rows]);
  const timeline = useMemo(() => nightTimeline(events, night, tz), [events, night, tz]);
  const timelineRows = useMemo(
    () =>
      timeline.map((e) => [
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
      ]),
    [timeline],
  );

  return (
    <View className="gap-8">
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
            {night.over ? (
              <StatTile
                label="Bedroom change"
                value={climate ? signedDegrees(climate.end - climate.start) : '–'}
                detail={climate ? `${climate.start.toFixed(1)} to ${climate.end.toFixed(1)}°C` : undefined}
              />
            ) : (
              // While the night is still going, how warm the room is now matters more than the change.
              <StatTile
                label="Bedroom now"
                value={climate ? `${climate.end.toFixed(1)}°C` : '–'}
                detail={climate ? `${signedDegrees(climate.end - climate.start)} since bed` : undefined}
              />
            )}
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
          <DataTable columns={TIMELINE_COLUMNS} rows={timelineRows} />
        ) : (
          <Text className="font-sans text-base text-ink-muted">
            {night.over ? 'Nothing from the pillow that night.' : 'Nothing from the pillow yet tonight.'}
          </Text>
        )}
      </View>
    </View>
  );
});
