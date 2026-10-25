import { Text } from 'react-native';

import { StatusWord } from '@/components/Status';
import type { PillowState } from '@/constants/status';
import type { NightTone } from '@/services/night';

/** Each outcome as a sentence around one key word, and the state colour that word takes. */
const HEADINGS: Record<NightTone, { before: string; word: string; after: string; state: PillowState }> = {
  quiet: { before: 'A ', word: 'quiet', after: ' night', state: 'asleep' },
  checked: { before: 'The pillow ', word: 'checked in', after: '', state: 'up' },
  alerted: { before: 'Family were ', word: 'alerted', after: '', state: 'up' },
  cold: { before: 'The room got ', word: 'cold', after: '', state: 'up' },
  hot: { before: 'The room got ', word: 'warm', after: '', state: 'up' },
  unknown: { before: 'The pillow was ', word: 'quiet', after: '', state: 'offline' },
};

/** "A *quiet* night": a summary card's heading, with the outcome as the one coloured word. */
export function NightHeading({ tone, soFar = false }: { tone: NightTone; soFar?: boolean }) {
  const h = HEADINGS[tone];
  return (
    <Text>
      {h.before}
      <StatusWord state={h.state}>{h.word}</StatusWord>
      {h.after}
      {soFar && tone === 'quiet' ? ' so far' : ''}
    </Text>
  );
}
