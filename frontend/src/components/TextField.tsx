import { Text, TextInput, type TextInputProps, View } from 'react-native';

import { useTheme } from '@/hooks/useTheme';

type TextFieldProps = TextInputProps & {
  label: string;
  /** Shown under the field, which also gets a danger border. */
  error?: string | null;
};

/** Filled input with its label above. Pass any TextInput prop (secureTextEntry, autoComplete, ...). */
export function TextField({ label, error, className, style, ...rest }: TextFieldProps) {
  const { colors } = useTheme();
  return (
    <View className="w-full gap-1.5">
      <Text className="font-sans-semibold text-xs text-ink-muted">{label}</Text>
      {/* Font size only, no line height or vertical padding: on a TextInput a line height pins the
          text to the top on iOS, and Android adds font padding, so the text sat off-centre. */}
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors['ink-muted']}
        textAlignVertical="center"
        className={`h-12 rounded-field border-[1.5px] bg-field px-4 py-0 font-sans text-[16px] text-ink ${
          error ? 'border-danger' : 'border-transparent focus:border-accent'
        } ${className ?? ''}`}
        style={[{ includeFontPadding: false }, style]}
        {...rest}
      />
      {error ? (
        <Text className="font-sans text-xs text-danger-text" accessibilityLiveRegion="polite">
          {error}
        </Text>
      ) : null}
    </View>
  );
}
