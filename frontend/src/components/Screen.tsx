import type { PropsWithChildren } from 'react';
import { ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

type ScreenProps = PropsWithChildren<{
  /** Centre the content (forms, empty states). Off for scrolling pages. */
  centered?: boolean;
  /** Scroll the content; the page background still fills the screen. */
  scroll?: boolean;
}>;

/** Safe-area-aware page on the theme's canvas. Wrap every screen in this. */
export function Screen({ centered = true, scroll = false, children }: ScreenProps) {
  const body = centered ? 'flex-1 items-center justify-center gap-2 p-4' : 'gap-4 p-4';
  return (
    <View className="flex-1 bg-canvas">
      <SafeAreaView style={{ flex: 1 }}>
        {scroll ? (
          <ScrollView contentContainerClassName={body}>{children}</ScrollView>
        ) : (
          <View className={centered ? body : `flex-1 ${body}`}>{children}</View>
        )}
      </SafeAreaView>
    </View>
  );
}
