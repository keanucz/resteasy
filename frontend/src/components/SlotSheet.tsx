import { useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Sheet } from '@/components/Feedback';
import { DateStrip, SpokenLine } from '@/components/ReminderForm';
import { StatusWord } from '@/components/Status';
import { ThemeRoot } from '@/components/ThemeRoot';
import { TimeSelect } from '@/components/TimeSelect';
import type { Reminder } from '@/services/reminders';
import {
  capitalise,
  dayMonth,
  formatClock,
  isPast,
  lowerDay,
  repeatWords,
  shiftDays,
  type Slot,
  thisDay,
  whenWords,
} from '@/services/schedule';

/** Days a reminder can be moved to from its sheet, from today. */
const MOVE_DAYS = 14;

/** How a reminder that already came due went, in words; the key word coloured only when it matters. */
function outcome(slot: Slot, name: string) {
  switch (slot.status) {
    case 'done':
      return { word: 'Done', state: 'asleep' as const, rest: `: ${name} said she'd done it.` };
    case 'announced':
      return { word: 'Reminded', rest: `: the pillow told ${name}.` };
    case 'missed':
      return { word: 'Not confirmed', state: 'up' as const, rest: `: ${name} didn't say she'd done it.` };
    case 'due':
      return { word: 'Reminding', rest: ` ${name} now.` };
    case 'waiting':
      return { word: 'Waiting', rest: `: ${name} is in bed or busy, so the pillow holds it until she's up.` };
    default:
      return null;
  }
}

/** Her consent to a reminder, in a sentence: what it means and what happens next. */
export function consentLine(consent: Slot['consent'], name: string): string | null {
  if (consent === 'pending')
    return `Waiting for ${name} to agree. The pillow will ask her, and it won't play until she says yes.`;
  if (consent === 'declined')
    return `${name} said no to this one, so it won't play. Have a word with her first: changing it asks her again.`;
  return null;
}

type SlotSheetProps = {
  slot: Slot | null;
  reminder: Reminder | undefined;
  name: string;
  today: string;
  now: string;
  onClose: () => void;
  onMove: (slot: Slot, date: string, time: string) => void;
  onSkip: (slot: Slot) => void;
  onEdit: (reminder: Reminder) => void;
};

/**
 * One time a reminder plays, opened from the calendar or the list: what she will hear and when,
 * whether she agreed, how it went if it has been. Moving it here (a day and a time) is the way to
 * move a reminder without dragging; skipping is one tap, with Undo after.
 */
export function SlotSheet({ slot, reminder, name, today, now, onClose, onMove, onSkip, onEdit }: SlotSheetProps) {
  return slot ? (
    <SlotSheetBody
      key={`${slot.reminder_id}:${slot.date}`}
      slot={slot}
      reminder={reminder}
      name={name}
      today={today}
      now={now}
      onClose={onClose}
      onMove={onMove}
      onSkip={onSkip}
      onEdit={onEdit}
    />
  ) : null;
}

function SlotSheetBody({
  slot,
  reminder,
  name,
  today,
  now,
  onClose,
  onMove,
  onSkip,
  onEdit,
}: SlotSheetProps & { slot: Slot }) {
  const [moving, setMoving] = useState(false);
  const [date, setDate] = useState(slot.date < today ? today : slot.date);
  const [time, setTime] = useState(slot.time);
  const past = isPast(slot.date, slot.time, today, now);
  const result = outcome(slot, name);
  const consent = consentLine(slot.consent, name);
  const repeat = reminder ? repeatWords(reminder, today) : slot.recurring ? 'repeats' : 'just this once';
  const targetPast = isPast(date, time, today, now);
  const unchanged = date === slot.date && time === slot.time;

  return (
    <Sheet
      visible
      title={capitalise(slot.label)}
      note={`${whenWords(slot.date, slot.time, today)}, ${dayMonth(slot.date)}. Plays ${repeat}.`}
      onClose={onClose}
    >
      <SpokenLine name={name} label={slot.label} />

      {result ? (
        <Text className="font-sans text-base leading-6 text-ink">
          {result.state ? (
            <StatusWord state={result.state}>{result.word}</StatusWord>
          ) : (
            <Text className="font-sans-semibold">{result.word}</Text>
          )}
          {result.rest}
        </Text>
      ) : null}
      {consent ? <Text className="font-sans text-base leading-6 text-ink-muted">{consent}</Text> : null}

      {!past ? (
        moving ? (
          <View className="gap-3">
            <Text className="font-sans-semibold text-xs text-ink-muted">Move to</Text>
            <DateStrip today={today} value={date} onChange={setDate} count={MOVE_DAYS} />
            <TimeSelect label="At" value={time} onChange={setTime} />
            <Text className="font-sans text-sm text-ink-muted">
              {targetPast
                ? 'That time has already gone. Pick a later one.'
                : `To ${lowerDay(whenWords(date, time, today))}. ${name} will be asked again before it plays.`}
            </Text>
            <Button
              fullWidth
              title="Move it"
              disabled={targetPast || unchanged}
              onPress={() => onMove(slot, date, time)}
            />
            <Button fullWidth variant="ghost" title="Keep it where it is" onPress={() => setMoving(false)} />
          </View>
        ) : (
          <View className="gap-2">
            <Button fullWidth title="Change day or time" onPress={() => setMoving(true)} />
            <Button
              fullWidth
              variant="secondary"
              title={slot.recurring ? `Skip ${thisDay(slot.date, today)}` : 'Cancel this one'}
              onPress={() => onSkip(slot)}
            />
          </View>
        )
      ) : null}

      {reminder ? <Button variant="ghost" title="Change the reminder" onPress={() => onEdit(reminder)} /> : null}
    </Sheet>
  );
}

type MoveChoiceProps = {
  /** The recurring reminder being moved, and from where to where. */
  move: { slot: Slot; reminder: Reminder; date: string; time: string } | null;
  name: string;
  today: string;
  onOnce: () => void;
  onEvery: () => void;
  onCancel: () => void;
};

/**
 * "Only this day, or every time?" for a recurring reminder that was moved: two big plain choices,
 * each saying what happens, and a quiet way out that puts it back.
 */
export function MoveChoice({ move, name, today, onOnce, onEvery, onCancel }: MoveChoiceProps) {
  if (!move) return null;
  const { slot, reminder, date, time } = move;
  const from = formatClock(slot.time);
  const days = shiftDays(reminder.days, slot.date, date);
  return (
    <Modal transparent animationType="fade" visible onRequestClose={onCancel}>
      {/* The modal renders outside the app root on web, so it needs its own theme variables. */}
      <ThemeRoot>
        <View className="flex-1 items-center justify-center bg-black/50 p-6">
          <View className="w-full max-w-sm gap-3 rounded-card bg-surface p-[18px]">
            <Text accessibilityRole="header" className="font-display text-lg text-ink">
              Move “{capitalise(slot.label)}” to {lowerDay(whenWords(date, time, today))}?
            </Text>
            <Text className="font-sans text-sm text-ink-muted">
              {name} will be asked again before it plays. Until she agrees, it stays quiet.
            </Text>
            <Choice
              title={`Only ${thisDay(slot.date, today)}`}
              detail={`Just this once. The other days stay at ${from}.`}
              onPress={onOnce}
            />
            <Choice
              title="Every time"
              detail={`From now on it plays ${repeatWords({ days, on_date: null }, today)} at ${formatClock(time)}.`}
              onPress={onEvery}
            />
            <Button fullWidth variant="ghost" title="Cancel, leave it" onPress={onCancel} />
          </View>
        </View>
      </ThemeRoot>
    </Modal>
  );
}

/** One of the two choices: a big button with its consequence under it. */
function Choice({ title, detail, onPress }: { title: string; detail: string; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${detail}`}
      onPress={onPress}
      className="min-h-16 justify-center gap-0.5 rounded-2xl bg-accent/25 px-4 py-3 active:opacity-80"
    >
      <Text className="font-sans-semibold text-base text-ink">{title}</Text>
      <Text className="font-sans text-[13px] text-ink-muted">{detail}</Text>
    </Pressable>
  );
}
