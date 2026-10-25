import { Pressable, Text, View } from 'react-native';

import { CheckIcon } from '@/components/TabIcons';
import { useTheme } from '@/hooks/useTheme';

export type RadioOption<T extends string> = { value: T; label: string; meta?: string };

type RadioListProps<T extends string> = {
  /** Read out before the options ("Accent"). */
  label: string;
  options: readonly RadioOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
};

/**
 * Pick one of a few options, each a row with a round check: the same look as choosing a voice,
 * so every choice on the voice screens reads alike.
 */
export function RadioList<T extends string>({ label, options, value, onChange }: RadioListProps<T>) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} className="gap-2">
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={`${option.label}${option.meta ? `. ${option.meta}` : ''}`}
            onPress={() => onChange(option.value)}
            className={`min-h-12 flex-row items-center gap-3 rounded-2xl border-[1.5px] bg-surface px-3.5 py-2.5 active:opacity-80 ${
              selected ? 'border-accent' : 'border-transparent'
            }`}
          >
            <View
              className={`size-6 items-center justify-center rounded-full border-[1.5px] ${
                selected ? 'border-accent bg-accent' : 'border-hairline'
              }`}
            >
              {selected ? <CheckIcon color={colors['on-accent']} size={14} /> : null}
            </View>
            <View className="flex-1 gap-0.5">
              <Text className="font-sans-semibold text-base text-ink">{option.label}</Text>
              {option.meta ? <Text className="font-sans text-[13px] text-ink-muted">{option.meta}</Text> : null}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}
