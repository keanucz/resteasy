import { Pressable, Switch, Text, View } from 'react-native';

import { useTheme } from '@/hooks/useTheme';

type ToggleProps = {
  value: boolean;
  onValueChange: (value: boolean) => void;
  /** Read out by screen readers. */
  label: string;
};

/** On/off switch in the accent colour with a white thumb. */
export function Toggle({ value, onValueChange, label }: ToggleProps) {
  const { colors } = useTheme();
  return (
    <Switch
      accessibilityLabel={label}
      value={value}
      onValueChange={onValueChange}
      trackColor={{ true: colors.accent, false: colors.hairline }}
      thumbColor="#FFFFFF"
      // react-native-web ignores thumbColor when on and falls back to teal; this web-only prop fixes it.
      {...({ activeThumbColor: '#FFFFFF' } as object)}
      ios_backgroundColor={colors.hairline}
    />
  );
}

type ChipProps = {
  label: string;
  selected: boolean;
  onPress: () => void;
};

/** Filter chip the user taps to include or exclude something. Not for showing status. */
export function Chip({ label, selected, onPress }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      className={`h-8 justify-center rounded-full border px-3.5 ${selected ? 'border-accent bg-accent' : 'border-hairline'}`}
    >
      <Text className={`font-sans-medium text-[13px] ${selected ? 'text-on-accent' : 'text-ink'}`}>{label}</Text>
    </Pressable>
  );
}

type SegmentedTabsProps<T extends string> = {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
};

/** Contained segmented control for switching views (Night, Week, Month). */
export function SegmentedTabs<T extends string>({ options, value, onChange }: SegmentedTabsProps<T>) {
  return (
    <View accessibilityRole="tablist" className="flex-row rounded-[10px] bg-surface p-[3px]">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            onPress={() => onChange(option.value)}
            className={`min-h-11 flex-1 items-center justify-center rounded-lg ${selected ? 'bg-ink/15' : ''}`}
          >
            <Text className={`font-sans-semibold text-[13px] ${selected ? 'text-ink' : 'text-ink-muted'}`}>
              {option.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

type CheckboxProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
};

/** Square checkbox with its label; ticks in the calm colour. */
export function Checkbox({ label, checked, onChange }: CheckboxProps) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      className="min-h-11 flex-row items-center gap-2.5"
    >
      <View
        className={`size-[22px] items-center justify-center rounded-md border-[1.5px] ${
          checked ? 'border-calm bg-calm' : 'border-hairline'
        }`}
      >
        {checked ? <Text className="font-sans-bold text-[13px] text-on-calm">✓</Text> : null}
      </View>
      <Text className="shrink font-sans text-base text-ink">{label}</Text>
    </Pressable>
  );
}
