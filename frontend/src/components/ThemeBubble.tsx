import { colorScheme } from 'nativewind';
import { createContext, type PropsWithChildren, useCallback, useContext } from 'react';
import { View } from 'react-native';

import { type Scheme } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';

type SwitchScheme = (next: Scheme) => void;

const ThemeBubbleContext = createContext<SwitchScheme>((next) => colorScheme.set(next));

/**
 * Changes between light and dark instantly: the new scheme is set straight away, with no
 * animation or overlay.
 */
export function ThemeBubbleProvider({ children }: PropsWithChildren) {
  const { scheme } = useTheme();

  const switchScheme = useCallback<SwitchScheme>(
    (next) => {
      if (next === scheme) return;
      colorScheme.set(next);
    },
    [scheme],
  );

  return (
    <ThemeBubbleContext.Provider value={switchScheme}>
      <View style={{ flex: 1 }}>{children}</View>
    </ThemeBubbleContext.Provider>
  );
}

/** Switch light and dark instantly. */
export function useSwitchScheme(): SwitchScheme {
  return useContext(ThemeBubbleContext);
}
