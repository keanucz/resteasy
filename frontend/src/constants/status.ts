/** The five states the app can show for the person being watched over. */
export type PillowState = 'asleep' | 'restless' | 'up' | 'alert' | 'offline';

/**
 * Status is always said in words: a sentence with one key word in the state's colour. Never a
 * pill, chip or badge (see the style guide). `before` and `after` wrap the key word.
 */
export function statusSentence(state: PillowState, name: string): { before: string; word: string; after: string } {
  switch (state) {
    case 'asleep':
      return { before: `${name} is `, word: 'asleep', after: '' };
    case 'restless':
      return { before: `${name} is `, word: 'restless', after: '' };
    case 'up':
      return { before: `${name} is `, word: 'up', after: '' };
    case 'alert':
      return { before: `${name} `, word: "hasn't come back", after: '' };
    case 'offline':
      return { before: 'The pillow is ', word: 'offline', after: '' };
  }
}

/** Text colour class per state. Full class names, so Tailwind's content scan keeps them. */
export const STATE_TEXT: Record<PillowState, string> = {
  asleep: 'text-state-asleep',
  restless: 'text-state-restless',
  up: 'text-state-up',
  alert: 'text-state-alert',
  offline: 'text-state-offline',
};
