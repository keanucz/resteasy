import type { PropsWithChildren, ReactNode } from 'react';
import { Pressable, Text, View } from 'react-native';

/** Stack of ListRows with the style guide's spacing. */
export function List({ children }: PropsWithChildren) {
  return <View className="gap-2.5">{children}</View>;
}

type ListRowProps = {
  title: string;
  meta?: string;
  /** Usually an <Avatar>. */
  leading?: ReactNode;
  /** Usually a <Toggle>, a <StatusWord> or a chevron. */
  trailing?: ReactNode;
  onPress?: () => void;
};

/** One row as its own card: leading, title and meta, trailing. */
export function ListRow({ title, meta, leading, trailing, onPress }: ListRowProps) {
  const content = (
    <>
      {leading}
      <View className="flex-1 gap-0.5">
        <Text className="font-sans-semibold text-base text-ink">{title}</Text>
        {meta ? <Text className="font-sans text-[13px] text-ink-muted">{meta}</Text> : null}
      </View>
      {trailing}
    </>
  );
  const row = 'flex-row items-center gap-3 rounded-2xl bg-surface px-3.5 py-3.5';
  return onPress ? (
    <Pressable accessibilityRole="button" onPress={onPress} className={`${row} active:opacity-80`}>
      {content}
    </Pressable>
  ) : (
    <View className={row}>{content}</View>
  );
}
