import { Text, View } from 'react-native';

type AvatarTone = 'accent' | 'danger' | 'muted';

type AvatarProps = {
  /** One or two letters, or a single glyph such as "!". */
  initials: string;
  tone?: AvatarTone;
  /** Smaller version for notifications. */
  small?: boolean;
};

const TONE: Record<AvatarTone, { fill: string; text: string }> = {
  accent: { fill: 'bg-accent/25', text: 'text-ink' },
  danger: { fill: 'bg-danger', text: 'text-on-danger' },
  muted: { fill: 'bg-hairline', text: 'text-ink-muted' },
};

/** Round initials badge for a person. */
export function Avatar({ initials, tone = 'accent', small = false }: AvatarProps) {
  return (
    <View
      accessible={false}
      className={`items-center justify-center rounded-full ${small ? 'size-9' : 'size-11'} ${TONE[tone].fill}`}
    >
      <Text className={`font-sans-semibold ${small ? 'text-sm' : 'text-base'} ${TONE[tone].text}`}>{initials}</Text>
    </View>
  );
}
