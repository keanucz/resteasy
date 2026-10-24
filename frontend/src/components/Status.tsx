import type { PropsWithChildren } from 'react';
import { Text } from 'react-native';

import { type PillowState, STATE_TEXT, statusSentence } from '@/constants/status';

type StatusWordProps = PropsWithChildren<{
  state: PillowState;
  /** Overrides the state colour, e.g. the sky's own ink. */
  color?: string;
}>;

/**
 * The status, said as one word inside a sentence: italic display serif in the state's colour.
 * Nest it in a <Text>. This replaces status pills, which the style guide bans.
 */
export function StatusWord({ state, color, children }: StatusWordProps) {
  return (
    <Text className={`font-display-italic ${color ? '' : STATE_TEXT[state]}`} style={color ? { color } : undefined}>
      {children}
    </Text>
  );
}

type StatusHeadlineProps = {
  state: PillowState;
  /** Who the pillow belongs to: "Mum". */
  name: string;
  /** Key word colour override (the sky passes its own ink). */
  wordColor?: string;
  className?: string;
};

/** "Mum is *asleep*": the status as the headline, only the key word coloured. */
export function StatusHeadline({ state, name, wordColor, className }: StatusHeadlineProps) {
  const { before, word, after } = statusSentence(state, name);
  return (
    <Text accessibilityRole="header" className={`font-display text-2xl leading-[30px] text-ink ${className ?? ''}`}>
      {before}
      <StatusWord state={state} color={wordColor}>
        {word}
      </StatusWord>
      {after}
    </Text>
  );
}
