import { useCallback, useMemo, useState } from 'react';
import { FlatList, Modal, Pressable, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { ThemeRoot } from '@/components/ThemeRoot';
import { useTheme } from '@/hooks/useTheme';
import { formatClock } from '@/services/schedule';

/** Choices every 15 minutes, all day. */
const STEP_MIN = 15;
const ROW_HEIGHT = 48;
/** Rows of context shown above the chosen time when the list opens. */
const ROWS_ABOVE = 2;

const pad = (n: number) => String(n).padStart(2, '0');

const TIMES = Array.from({ length: (24 * 60) / STEP_MIN }, (_, i) => {
  const minutes = i * STEP_MIN;
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
});

type TimeSelectProps = {
  label: string;
  /** "HH:MM", 24 hour; undefined while it loads. */
  value: string | undefined;
  onChange: (hhmm: string) => void;
  disabled?: boolean;
};

/**
 * A time picked from a scrolling list rather than typed: the field shows the time, a tap opens
 * every quarter hour of the day with the current one in view, a tap on a time picks it.
 */
export function TimeSelect({ label, value, onChange, disabled = false }: TimeSelectProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  // A saved time off the 15-minute grid still shows, as its own row.
  const times = useMemo(() => (value && !TIMES.includes(value) ? [...TIMES, value].sort() : TIMES), [value]);
  const selected = value ? times.indexOf(value) : -1;

  const pick = useCallback(
    (hhmm: string) => {
      setOpen(false);
      if (hhmm !== value) onChange(hhmm);
    },
    [onChange, value],
  );

  return (
    <View className="w-full gap-1.5">
      <Text className="font-sans-semibold text-xs text-ink-muted">{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}, ${value ? formatClock(value) : 'not set'}`}
        accessibilityHint="Opens a list of times"
        disabled={disabled || !value}
        onPress={() => setOpen(true)}
        className="h-12 flex-row items-center justify-between rounded-field bg-field px-4 active:opacity-80"
      >
        <Text className={`font-sans text-[16px] ${value ? 'text-ink' : 'text-ink-muted'}`}>
          {value ? formatClock(value) : '–'}
        </Text>
        <Svg width={16} height={16} viewBox="0 0 24 24" accessible={false}>
          <Path
            d="M6 9 L12 15 L18 9"
            stroke={colors['ink-muted']}
            strokeWidth={2}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      </Pressable>

      <Modal transparent animationType="fade" visible={open} onRequestClose={() => setOpen(false)}>
        {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
        <ThemeRoot>
          <Pressable
            accessibilityLabel="Close"
            onPress={() => setOpen(false)}
            className="flex-1 items-center justify-center bg-black/50 p-6"
          >
            {/* Stops a tap inside the list from closing it. */}
            <Pressable
              className="max-h-[420px] w-full max-w-sm gap-2 rounded-card bg-surface p-[18px]"
              onPress={() => {}}
            >
              <Text className="font-display text-lg text-ink">{label}</Text>
              <FlatList
                data={times}
                keyExtractor={(t) => t}
                initialScrollIndex={Math.max(0, selected - ROWS_ABOVE)}
                getItemLayout={(_, index) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * index, index })}
                showsVerticalScrollIndicator
                renderItem={({ item, index }) => (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ selected: index === selected }}
                    onPress={() => pick(item)}
                    style={{ height: ROW_HEIGHT }}
                    className={`justify-center rounded-lg px-3.5 active:opacity-70 ${index === selected ? 'bg-ink/15' : ''}`}
                  >
                    <Text
                      className={`text-base ${index === selected ? 'font-sans-semibold text-ink' : 'font-sans text-ink-muted'}`}
                    >
                      {formatClock(item)}
                    </Text>
                  </Pressable>
                )}
              />
            </Pressable>
          </Pressable>
        </ThemeRoot>
      </Modal>
    </View>
  );
}
