import { type ReactNode, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { ChevronIcon } from '@/components/TabIcons';
import { useTheme } from '@/hooks/useTheme';

type DisclosureProps = {
  /** What the hidden part is for ("Tone"). */
  title: string;
  /** What is chosen now, said after the title ("Calm"). */
  value?: string;
  children: ReactNode;
};

/**
 * A row that opens to show a longer choice (a list of tones or accents, a form), so the voice
 * page stays short until someone wants that part. The row says what is chosen while closed.
 */
export function Disclosure({ title, value, children }: DisclosureProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  return (
    <View className="gap-2">
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={value ? `${title}: ${value}` : title}
        onPress={() => setOpen((o) => !o)}
        className="min-h-12 flex-row items-center gap-3 rounded-2xl bg-surface px-3.5 py-3 active:opacity-80"
      >
        <Text className="flex-1 font-sans text-base text-ink">
          <Text className="font-sans-semibold">{title}</Text>
          {value ? `: ${value}` : ''}
        </Text>
        <Text className="font-sans-semibold text-sm text-accent-text">{open ? 'Close' : 'Change'}</Text>
        <View style={{ transform: [{ rotate: open ? '-90deg' : '90deg' }] }}>
          <ChevronIcon color={colors['ink-muted']} size={16} />
        </View>
      </Pressable>
      {open ? children : null}
    </View>
  );
}
