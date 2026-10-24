import { useLocalSearchParams } from 'expo-router';
import { useColorScheme } from 'nativewind';
import { useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { AppText } from '@/components/AppText';
import { Avatar } from '@/components/Avatar';
import { Button } from '@/components/Button';
import { Card } from '@/components/Card';
import { DialogCard, NotificationCard } from '@/components/Feedback';
import { List, ListRow } from '@/components/List';
import { NightRibbon, type RibbonSegment } from '@/components/NightRibbon';
import { Checkbox, Chip, SegmentedTabs, Toggle } from '@/components/Selection';
import { ListRowSkeleton, SkeletonGroup, StatTileSkeleton, SummaryCardSkeleton } from '@/components/Skeleton';
import { SkyHeader } from '@/components/SkyHeader';
import { DataTable, StatTile, SummaryCard } from '@/components/Stats';
import { StatusWord } from '@/components/Status';
import { TextField } from '@/components/TextField';
import type { PillowState } from '@/constants/status';

const STATES = [
  { value: 'asleep', label: 'Asleep' },
  { value: 'restless', label: 'Restless' },
  { value: 'up', label: 'Up' },
  { value: 'alert', label: 'Alert' },
  { value: 'offline', label: 'Offline' },
] as const;

/** Demo data for each state, as on the moodboard. Times are hours after 10 pm. */
const DEMO: Record<PillowState, { detail: string; ribbon: RibbonSegment[] }> = {
  asleep: { detail: 'In bed since 10:42 pm. Settled since 11:05 pm.', ribbon: [{ kind: 'bed', from: 0.7, to: 4.38 }] },
  restless: {
    detail: 'Turning over a lot since 1:50 am.',
    ribbon: [
      { kind: 'bed', from: 0.7, to: 3.83 },
      { kind: 'restless', from: 3.83, to: 4.38 },
    ],
  },
  up: {
    detail: 'Out of bed since 2:14 am. The path light is on.',
    ribbon: [
      { kind: 'bed', from: 0.7, to: 4.23 },
      { kind: 'up', from: 4.23, to: 4.38 },
    ],
  },
  alert: {
    detail: "Up for 9 minutes and she didn't answer the pillow.",
    ribbon: [
      { kind: 'bed', from: 0.7, to: 4.23 },
      { kind: 'alert', from: 4.23, to: 4.38 },
    ],
  },
  offline: {
    detail: "Last heard from at 11:58 pm. Check it's plugged in.",
    ribbon: [
      { kind: 'bed', from: 0.7, to: 1.97 },
      { kind: 'unknown', from: 1.97, to: 4.38 },
    ],
  },
};

/** Section heading inside the style guide. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View className="gap-3">
      <AppText variant="label">{title}</AppText>
      {children}
    </View>
  );
}

const isState = (value: unknown): value is PillowState => STATES.some((s) => s.value === value);

/**
 * Living style guide: every component in the current colour scheme. Dev tool, not a product screen.
 * Deep-link a look with `/styleguide?state=alert&scheme=light`.
 */
export default function StyleguideScreen() {
  const params = useLocalSearchParams<{ state?: string; scheme?: string }>();
  const { colorScheme, setColorScheme } = useColorScheme();
  const [state, setState] = useState<PillowState>(isState(params.state) ? params.state : 'asleep');

  useEffect(() => {
    if (params.scheme === 'light' || params.scheme === 'dark') setColorScheme(params.scheme);
  }, [params.scheme, setColorScheme]);
  const [alerts, setAlerts] = useState(true);
  const [chips, setChips] = useState({ up: true, alerts: true, quiet: false });
  const [range, setRange] = useState<'night' | 'week' | 'month'>('night');
  const [checked, setChecked] = useState(true);

  return (
    <ScrollView className="flex-1 bg-canvas" contentContainerClassName="pb-16">
      <SkyHeader state={state} name="Mum" initials="M" detail={DEMO[state].detail} />
      <View className="gap-8 px-4">
        <View className="gap-3">
          <SegmentedTabs options={STATES} value={state} onChange={setState} />
          <Button
            variant="secondary"
            title={colorScheme === 'dark' ? 'Show light mode' : 'Show dark mode'}
            onPress={() => setColorScheme(colorScheme === 'dark' ? 'light' : 'dark')}
          />
        </View>

        <Section title="Tonight">
          <Card>
            <NightRibbon segments={DEMO[state].ribbon} now={4.38} />
          </Card>
          <View className="flex-row gap-2.5">
            <StatTile label="Asleep for" value="3h 18m" />
            <StatTile label="Out of bed" value="Once" />
          </View>
        </Section>

        <Section title="Last night">
          <SummaryCard
            heading={
              <>
                A <StatusWord state="asleep">quiet</StatusWord> night
              </>
            }
            body="Mum was in bed by 10:42 pm, got up once at 2:14 am and was back within 5 minutes."
          />
          <DataTable
            columns={['Night', 'In bed', 'Got up', 'Woke']}
            rows={[
              ['Mon', '10:31 pm', 'No', '6:58 am'],
              ['Tue', '10:42 pm', <Text key="t" className="text-sm"><StatusWord state="up">Once</StatusWord></Text>, '7:05 am'],
              ['Wed', '11:02 pm', <Text key="w" className="text-sm"><StatusWord state="up">2 times</StatusWord></Text>, '7:20 am'],
              ['Thu', '10:38 pm', 'No', '6:51 am'],
            ]}
          />
        </Section>

        <Section title="Status in words">
          <Text className="font-display text-lg text-ink">
            Mum is <StatusWord state="asleep">asleep</StatusWord>
          </Text>
          <Text className="font-display text-lg text-ink">
            Mum is <StatusWord state="restless">restless</StatusWord>
          </Text>
          <Text className="font-display text-lg text-ink">
            Mum is <StatusWord state="up">up</StatusWord>, path light on
          </Text>
          <Text className="font-display text-lg text-ink">
            Mum <StatusWord state="alert">needs you</StatusWord>
          </Text>
          <Text className="font-display text-lg text-ink">
            The pillow is <StatusWord state="offline">offline</StatusWord>
          </Text>
        </Section>

        <Section title="Buttons">
          <Button title="I'm on it" onPress={() => {}} />
          <Button variant="secondary" title="Call Mum" onPress={() => {}} />
          <Button variant="alert" title="Call emergency contact" onPress={() => {}} />
          <Button variant="ghost" title="Not now" onPress={() => {}} />
          <Button title="Saving" loading onPress={() => {}} />
          <Button title="Disabled" disabled onPress={() => {}} />
        </Section>

        <Section title="Fields">
          <TextField label="Say something to Mum" placeholder="The pillow reads it out" />
          <TextField label="Phone number" defaultValue="0123" error="That number looks too short." />
        </Section>

        <Section title="Care circle">
          <List>
            <ListRow
              leading={<Avatar initials="SZ" />}
              title="You"
              meta="Gets the first alert"
              trailing={<Toggle label="Alerts for you" value={alerts} onValueChange={setAlerts} />}
            />
            <ListRow
              leading={<Avatar initials="AN" />}
              title="Anna"
              meta="Second, after 2 minutes"
              trailing={<Toggle label="Alerts for Anna" value onValueChange={() => {}} />}
            />
            <ListRow
              leading={<Avatar initials="TO" tone="muted" />}
              title="Tom"
              meta="Quiet hours 10 pm to 7 am"
              trailing={<Toggle label="Alerts for Tom" value={false} onValueChange={() => {}} />}
            />
          </List>
        </Section>

        <Section title="Choosing">
          <View className="flex-row flex-wrap gap-2">
            <Chip label="Got up" selected={chips.up} onPress={() => setChips({ ...chips, up: !chips.up })} />
            <Chip label="Alerts" selected={chips.alerts} onPress={() => setChips({ ...chips, alerts: !chips.alerts })} />
            <Chip label="Quiet nights" selected={chips.quiet} onPress={() => setChips({ ...chips, quiet: !chips.quiet })} />
          </View>
          <SegmentedTabs
            options={[
              { value: 'night', label: 'Night' },
              { value: 'week', label: 'Week' },
              { value: 'month', label: 'Month' },
            ]}
            value={range}
            onChange={setRange}
          />
          <Checkbox label="Turn on the path light when she gets up" checked={checked} onChange={setChecked} />
        </Section>

        <Section title="Loading (ghost)">
          <SkeletonGroup>
            <View className="gap-2.5">
              <View className="flex-row gap-2.5">
                <StatTileSkeleton />
                <StatTileSkeleton />
              </View>
              <SummaryCardSkeleton />
              <ListRowSkeleton />
            </View>
          </SkeletonGroup>
        </Section>

        <Section title="Notifications and dialogs">
          <NotificationCard initials="M" title="Mum is back in bed" detail="Path light turned off" time="now" />
          <NotificationCard alert initials="M" title="Mum got up at 2:14 am and hasn't come back" detail="Tap to check on her" time="2:21" />
          <DialogCard
            title="Add Anna to the care circle?"
            body="She'll get alerts when you're asleep or don't answer."
            confirmLabel="Invite Anna"
            onConfirm={() => {}}
            onCancel={() => {}}
          />
        </Section>
      </View>
    </ScrollView>
  );
}
