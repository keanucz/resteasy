import { memo, useCallback, useRef, useState } from 'react';
import { FlatList, Modal, Pressable, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { ThemeRoot } from '@/components/ThemeRoot';
import { useTheme } from '@/hooks/useTheme';

const ROW_HEIGHT = 48;

/** Every row is the same height, so the list can open on the chosen one without measuring. */
const itemLayout = (_: unknown, index: number) => ({ length: ROW_HEIGHT, offset: ROW_HEIGHT * index, index });

export type Option = { value: string; label: string };

type OptionSelectProps = {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  disabled?: boolean;
};

/**
 * A dropdown: the field shows the chosen option, a tap opens the list of them, a tap on one picks
 * it. The same look as TimeSelect.
 */
export const OptionSelect = memo(function OptionSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: OptionSelectProps) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  // Whether the list still takes a pick: a second tap while it fades out must not pick again.
  const picking = useRef(false);
  const selected = options.findIndex((o) => o.value === value);
  const shown = options[selected]?.label ?? value;

  const show = useCallback(() => {
    picking.current = true;
    setOpen(true);
  }, []);

  const close = useCallback(() => {
    picking.current = false;
    setOpen(false);
  }, []);

  const pick = useCallback(
    (next: string) => {
      if (!picking.current) return;
      close();
      if (next !== value) onChange(next);
    },
    [close, onChange, value],
  );

  const renderItem = useCallback(
    ({ item, index }: { item: Option; index: number }) => (
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ selected: index === selected }}
        onPress={() => pick(item.value)}
        style={{ height: ROW_HEIGHT }}
        className={`justify-center rounded-lg px-3.5 active:opacity-70 ${index === selected ? 'bg-ink/15' : ''}`}
      >
        <Text className={`text-base ${index === selected ? 'font-sans-semibold text-ink' : 'font-sans text-ink-muted'}`}>
          {item.label}
        </Text>
      </Pressable>
    ),
    [pick, selected],
  );

  return (
    <View className="w-full gap-1.5">
      <Text className="font-sans-semibold text-xs text-ink-muted">{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}, ${shown}`}
        accessibilityHint="Opens a list to choose from"
        disabled={disabled}
        onPress={show}
        className={`h-12 flex-row items-center justify-between rounded-field bg-field px-4 active:opacity-80 ${disabled ? 'opacity-60' : ''}`}
      >
        <Text className="font-sans text-[16px] text-ink">{shown}</Text>
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

      <Modal transparent animationType="fade" visible={open} onRequestClose={close}>
        {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
        <ThemeRoot>
          <Pressable
            accessibilityLabel="Close"
            onPress={close}
            className="flex-1 items-center justify-center bg-black/50 p-6"
          >
            {/* Stops a tap inside the list from closing it. */}
            <Pressable
              className="max-h-[520px] w-full max-w-sm gap-2 rounded-card bg-surface p-[18px]"
              onPress={() => {}}
            >
              <Text className="font-display text-lg text-ink">{label}</Text>
              <FlatList
                data={options}
                keyExtractor={(o) => o.value}
                initialScrollIndex={Math.max(0, selected)}
                getItemLayout={itemLayout}
                showsVerticalScrollIndicator
                renderItem={renderItem}
              />
            </Pressable>
          </Pressable>
        </ThemeRoot>
      </Modal>
    </View>
  );
});
