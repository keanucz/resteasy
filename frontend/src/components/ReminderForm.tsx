import { type ComponentType, useMemo, useState } from 'react';
import { type ColorValue, Pressable, ScrollView, Text, View } from 'react-native';

import { Button } from '@/components/Button';
import { Sheet } from '@/components/Feedback';
import { SegmentedTabs, Toggle } from '@/components/Selection';
import { GlassIcon, MoonIcon, PhoneIcon, PillIcon } from '@/components/TabIcons';
import { TextField } from '@/components/TextField';
import { TimeSelect } from '@/components/TimeSelect';
import { usePillowLink } from '@/hooks/usePillowLink';
import { useTheme } from '@/hooks/useTheme';
import { ApiError } from '@/services/api';
import {
  createReminder,
  deleteReminder,
  EVERY_DAY,
  type Reminder,
  type ReminderChange,
  type ReminderKind,
  updateReminder,
  WEEKDAYS,
} from '@/services/reminders';
import {
  addDays,
  consentQuestion,
  dayMonth,
  dayName,
  formatClock,
  isoWeekday,
  relativeDay,
  repeatWords,
  spokenClock,
  spokenLine,
  tidyLabel,
} from '@/services/schedule';

type Repeat = 'once' | 'daily' | 'weekdays' | 'days';

const REPEATS: readonly { value: Repeat; label: string }[] = [
  { value: 'once', label: 'Once' },
  { value: 'daily', label: 'Every day' },
  { value: 'weekdays', label: 'Weekdays' },
  { value: 'days', label: 'Pick days' },
];

const KINDS: readonly { value: ReminderKind; label: string }[] = [
  { value: 'meds', label: 'Medicine' },
  { value: 'call', label: 'A call' },
  { value: 'custom', label: 'Other' },
];

type IconComponent = ComponentType<{ color: ColorValue; size?: number }>;

/** A head start for the reminders families set most. Labels never name a drug (visitors may hear it). */
type Template = {
  key: string;
  title: string;
  icon: IconComponent;
  kind: ReminderKind;
  label: string;
  time: string;
  repeat: Repeat;
  days?: number[];
  confirm: boolean;
};

const TEMPLATES: readonly Template[] = [
  {
    key: 'tablets',
    title: 'Tablets',
    icon: PillIcon,
    kind: 'meds',
    label: 'take your morning tablets',
    time: '08:00',
    repeat: 'daily',
    confirm: true,
  },
  {
    key: 'water',
    title: 'Water',
    icon: GlassIcon,
    kind: 'custom',
    label: 'have a glass of water',
    time: '10:30',
    repeat: 'daily',
    confirm: false,
  },
  {
    key: 'call',
    title: 'A call',
    icon: PhoneIcon,
    kind: 'call',
    label: 'have a chat with the family',
    time: '18:00',
    repeat: 'days',
    days: [7],
    confirm: false,
  },
  {
    key: 'wind',
    title: 'Bedtime',
    icon: MoonIcon,
    kind: 'custom',
    label: 'start getting ready for bed',
    time: '21:00',
    repeat: 'daily',
    confirm: false,
  },
];

/** More than this many words, or two things joined by "and", is hard to take in when spoken. */
const LONG_LABEL_WORDS = 8;
/** Days offered for a one-off reminder, from today. */
const DATE_CHOICES = 21;
/** The backend's limit on a label. */
const LABEL_MAX = 80;
/** From 10 pm to 7 am she is usually in bed, and the pillow holds a reminder while she is. */
const NIGHT_FROM = '22:00';
const NIGHT_UNTIL = '07:00';

const DAY_LETTERS = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Same members, in any order. */
const sameSet = <T,>(a: T[], b: T[]) => a.length === b.length && a.every((x) => b.includes(x));

function repeatOf(r: Reminder): Repeat {
  if (r.on_date) return 'once';
  if (sameSet(r.days, EVERY_DAY)) return 'daily';
  if (sameSet(r.days, WEEKDAYS)) return 'weekdays';
  return 'days';
}

/** Why a save failed, in words. The Guardian screens labels; its reason comes back on a 422. */
function saveError(e: unknown): string {
  if (e instanceof ApiError && e.status === 422) {
    const reason = e.message.replace(/^label:\s*/, '');
    return `The pillow won't say that: ${reason}`;
  }
  if (e instanceof ApiError && (e.status === 404 || e.status === 405)) return "This pillow can't take reminders yet.";
  return "Couldn't save it. Check your connection and try again.";
}

type ReminderFormProps = {
  visible: boolean;
  pillowId: string;
  /** Her name, as the pillow says it. */
  name: string;
  today: string;
  /** "HH:MM" now on her clock, so a time already gone today starts tomorrow. */
  now: string;
  /** The reminder to edit, or null to add one. */
  reminder: Reminder | null;
  onClose: () => void;
  /** Saved (or deleted): what to tell the family. */
  onDone: (message: string, detail?: string) => void;
};

/**
 * Add or change a reminder. The simple path is three choices: what (a template or her own words,
 * with the exact sentence she will hear), when, and how often. Asking her to confirm, the kind and
 * how it reaches her sit under "More options". Every save that changes what she hears, or when,
 * says it asks her again.
 */
export function ReminderForm({ visible, reminder, ...rest }: ReminderFormProps) {
  // A fresh form each time it opens, so a half-made reminder never lingers into the next.
  return visible ? <Form key={reminder?.id ?? 'new'} reminder={reminder} {...rest} /> : null;
}

function Form({ pillowId, name, today, now, reminder, onClose, onDone }: Omit<ReminderFormProps, 'visible'>) {
  const editing = reminder !== null;
  // Who the pillow says is asking: whoever set it up, else the person signed in on this phone.
  const { myName } = usePillowLink();
  const asker = reminder?.created_by_name ?? myName;
  const [label, setLabel] = useState(reminder?.label ?? '');
  const [kind, setKind] = useState<ReminderKind>(reminder?.kind ?? 'custom');
  const [time, setTime] = useState(reminder?.time_of_day ?? '09:00');
  const [repeat, setRepeat] = useState<Repeat>(reminder ? repeatOf(reminder) : 'daily');
  const [date, setDate] = useState(reminder?.on_date ?? today);
  const [days, setDays] = useState<number[]>(reminder && !reminder.on_date ? reminder.days : [isoWeekday(today)]);
  const [confirm, setConfirm] = useState(reminder?.confirm ?? false);
  const [active, setActive] = useState(reminder?.active ?? true);
  const [skips, setSkips] = useState(reminder?.skip_dates ?? []);
  const [more, setMore] = useState(false);
  const [template, setTemplate] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const words = tidyLabel(label);
  const ruleDays = repeat === 'daily' ? EVERY_DAY : repeat === 'weekdays' ? WEEKDAYS : days;
  const onDate = repeat === 'once' ? date : null;
  const gone = repeat === 'once' && date === today && time <= now;
  const valid = words.length > 0 && (repeat !== 'days' || days.length > 0) && !gone;
  const long = words.split(/\s+/).length > LONG_LABEL_WORDS || /\band\b/i.test(words);
  const night = time >= NIGHT_FROM || time < NIGHT_UNTIL;

  // What is sent: only what changed when editing.
  const change = useMemo((): ReminderChange => {
    const next: ReminderChange = { label: words, kind, time_of_day: time, confirm };
    if (onDate) next.on_date = onDate;
    else {
      next.days = [...ruleDays].sort();
      next.on_date = null;
    }
    if (!reminder) return next;
    const diff: ReminderChange = {};
    if (words !== reminder.label) diff.label = words;
    if (kind !== reminder.kind) diff.kind = kind;
    if (time !== reminder.time_of_day) diff.time_of_day = time;
    if (confirm !== reminder.confirm) diff.confirm = confirm;
    if (onDate !== reminder.on_date) diff.on_date = onDate;
    if (!onDate && !sameSet(ruleDays, reminder.days)) diff.days = [...ruleDays].sort();
    if (active !== reminder.active) diff.active = active;
    if (!sameSet(skips, reminder.skip_dates)) diff.skip_dates = skips;
    return diff;
  }, [words, kind, time, confirm, onDate, ruleDays, reminder, active, skips]);

  // Changing the words, the time or the days means she is asked again (the backend resets consent).
  const asksAgain = !reminder || ['label', 'time_of_day', 'days', 'on_date'].some((k) => k in change);
  const changed = Object.keys(change).length > 0;

  const first = useMemo(() => {
    if (onDate) return onDate;
    for (let i = 0; i < 8; i++) {
      const d = addDays(today, i);
      if (i === 0 && time <= now) continue;
      if (ruleDays.includes(isoWeekday(d))) return d;
    }
    return today;
  }, [onDate, ruleDays, today, now, time]);
  const firstDay = relativeDay(first, today);
  const firstWords = firstDay === 'Today' || firstDay === 'Tomorrow' ? firstDay.toLowerCase() : `on ${firstDay}`;

  const applyTemplate = (t: Template) => {
    setTemplate(t.key);
    setLabel(t.label);
    setKind(t.kind);
    setTime(t.time);
    setRepeat(t.repeat);
    if (t.days) setDays(t.days);
    setConfirm(t.confirm);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      if (!reminder) {
        await createReminder(pillowId, {
          label: words,
          kind,
          time_of_day: time,
          ...(onDate ? { on_date: onDate } : { days: [...ruleDays].sort() }),
          confirm,
          channels: ['voice'],
        });
        onDone('Reminder saved', `The pillow will ask ${name} if that's alright.`);
      } else {
        await updateReminder(pillowId, reminder.id, change);
        onDone('Saved', asksAgain ? `${name} will be asked again before it plays.` : undefined);
      }
    } catch (e) {
      setError(saveError(e));
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!reminder) return;
    setSaving(true);
    try {
      await deleteReminder(pillowId, reminder.id);
      onDone('Reminder deleted', `The pillow won't say it to ${name} again.`);
    } catch (e) {
      setError(saveError(e));
      setSaving(false);
    }
  };

  const consentNote = !reminder
    ? undefined
    : !reminder.active
      ? "Paused. It won't play until you turn it back on."
      : reminder.consent === 'pending'
        ? `Waiting for ${name} to agree. It won't play until she does.`
        : reminder.consent === 'declined'
          ? `${name} said no to this one, so it won't play. Have a word with her first: changing it asks her again.`
          : reminder.consent_at
            ? `${name} agreed on ${dayName(reminder.consent_at.slice(0, 10))} ${dayMonth(reminder.consent_at.slice(0, 10))}.`
            : undefined;

  const footer = (
    <>
      {error ? (
        <Text accessibilityLiveRegion="polite" className="font-sans text-sm text-danger-text">
          {error}
        </Text>
      ) : null}
      <Button
        fullWidth
        title={!reminder ? `Save and ask ${name}` : asksAgain ? `Save and ask ${name} again` : 'Save'}
        loading={saving}
        disabled={!valid || (editing && !changed)}
        onPress={save}
      />
    </>
  );

  return (
    <Sheet
      visible
      title={editing ? 'Change reminder' : 'New reminder'}
      note={consentNote}
      onClose={onClose}
      footer={footer}
    >
      {!editing ? (
        <View className="gap-2">
          <Text className="font-sans-semibold text-xs text-ink-muted">Start from</Text>
          <View className="flex-row gap-2">
            {TEMPLATES.map((t) => (
              <TemplateTile key={t.key} template={t} selected={template === t.key} onPress={() => applyTemplate(t)} />
            ))}
          </View>
        </View>
      ) : null}

      <View className="gap-3">
        <TextField
          label="What should the pillow remind her to do?"
          value={label}
          onChangeText={(text) => {
            setLabel(text);
            setTemplate(null);
          }}
          placeholder="take your heart tablets"
          maxLength={LABEL_MAX}
          autoCapitalize="none"
          returnKeyType="done"
        />
        <SpokenLine name={name} label={words} />
        {long ? (
          <Text className="font-sans text-sm text-ink-muted">
            Shorter works better spoken. One thing per reminder is easier to remember.
          </Text>
        ) : null}
      </View>

      <View className="gap-3">
        <TimeSelect label="At" value={time} onChange={setTime} />
        <View className="gap-1.5">
          <Text className="font-sans-semibold text-xs text-ink-muted">How often</Text>
          <SegmentedTabs options={REPEATS} value={repeat} onChange={setRepeat} />
        </View>
        {repeat === 'once' ? <DateStrip today={today} value={date} onChange={setDate} count={DATE_CHOICES} /> : null}
        {repeat === 'days' ? <DayPicker value={days} onChange={setDays} /> : null}
        <Text className="font-sans text-sm text-ink">
          {valid
            ? `Plays ${repeatWords({ days: ruleDays, on_date: onDate }, today)} at ${formatClock(time)}.${
                onDate ? '' : ` The first is ${firstWords}.`
              }`
            : gone
              ? 'That time has already gone today. Pick a later time or another day.'
              : repeat === 'days' && !days.length
                ? 'Pick at least one day.'
                : 'Say what it should remind her to do.'}
        </Text>
        {night ? (
          <Text className="font-sans text-sm text-ink-muted">
            {`That's at night. If ${name} is in bed then, the pillow waits until she's up.`}
          </Text>
        ) : null}
      </View>

      <View className="gap-3">
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ expanded: more }}
          onPress={() => setMore(!more)}
          className="min-h-11 flex-row items-center justify-between active:opacity-70"
        >
          <Text className="font-sans-semibold text-base text-ink">More options</Text>
          <Text className="font-sans text-sm text-ink-muted">
            {more ? 'Hide' : confirm ? `${name} confirms` : 'Show'}
          </Text>
        </Pressable>
        {more ? (
          <View className="gap-4">
            <OptionRow
              title={`Ask ${name} to say she's done it`}
              meta="If she doesn't, the pillow asks once more ten minutes later."
              trailing={<Toggle label={`Ask ${name} to confirm`} value={confirm} onValueChange={setConfirm} />}
            />
            <View className="gap-1.5">
              <Text className="font-sans-semibold text-xs text-ink-muted">Kind</Text>
              <SegmentedTabs options={KINDS} value={kind} onChange={setKind} />
            </View>
            <Text className="font-sans text-sm text-ink-muted">
              The pillow says it out loud, in the voice chosen in Settings. Texts and emails come later.
            </Text>
          </View>
        ) : null}
      </View>

      <View className="gap-1.5 rounded-2xl border border-hairline p-3.5">
        <Text className="font-sans-semibold text-xs text-ink-muted">
          {!asksAgain
            ? `${name} has already said yes to this`
            : asker
              ? `Before it plays, the pillow asks ${name}`
              : `The pillow will ask ${name} something like`}
        </Text>
        {asksAgain ? (
          <Text className="font-display-regular text-[15px] leading-6 text-ink">
            “{consentQuestion(asker, words || '…', time, ruleDays, onDate)}”
          </Text>
        ) : (
          <Text className="font-sans text-sm text-ink-muted">
            Changing what she hears, the time or the days asks her again.
          </Text>
        )}
      </View>

      {editing && reminder ? (
        <View className="gap-4">
          <OptionRow
            title="Pause it"
            meta={active ? 'Stops it playing for a while, without losing it.' : "Paused. It won't play."}
            trailing={<Toggle label="Pause it" value={!active} onValueChange={(paused) => setActive(!paused)} />}
          />
          {skips.filter((d) => d >= today).length ? (
            <View className="gap-2">
              <Text className="font-sans-semibold text-xs text-ink-muted">Skipped days</Text>
              {skips
                .filter((d) => d >= today)
                .sort()
                .map((d) => (
                  <OptionRow
                    key={d}
                    title={`${relativeDay(d, today)}, ${dayMonth(d)}`}
                    trailing={
                      <Button variant="ghost" title="Put back" onPress={() => setSkips(skips.filter((s) => s !== d))} />
                    }
                  />
                ))}
            </View>
          ) : null}
          {deleting ? (
            <View className="gap-2 rounded-2xl bg-surface p-3.5">
              <Text className="font-sans text-sm text-ink">
                Delete “{reminder.label}” for good? {name} {"won't"} hear it again.
              </Text>
              <View className="flex-row gap-2">
                <View className="flex-1">
                  <Button fullWidth variant="secondary" title="Delete" loading={saving} onPress={remove} />
                </View>
                <View className="flex-1">
                  <Button fullWidth variant="ghost" title="Keep it" onPress={() => setDeleting(false)} />
                </View>
              </View>
            </View>
          ) : (
            <Button variant="ghost" title="Delete this reminder" onPress={() => setDeleting(true)} />
          )}
        </View>
      ) : null}
    </Sheet>
  );
}

/**
 * The sentence she will hear, in the serif the app keeps for words said aloud. With nothing typed
 * yet the gap shows where her reminder goes.
 */
export function SpokenLine({
  name,
  label,
  heading,
  small = false,
}: {
  name: string;
  label: string;
  /** The line above the sentence; "Margaret will hear" unless given (a "when", so it reads stronger). */
  heading?: string;
  small?: boolean;
}) {
  const top = heading ?? `${name} will hear`;
  return (
    <View className="gap-1" accessible accessibilityLabel={`${top}: ${spokenLine(name, label || '...')}`}>
      <Text className={heading ? 'font-sans-semibold text-sm text-ink' : 'font-sans-semibold text-xs text-ink-muted'}>
        {top}
      </Text>
      <Text className={`font-display-italic text-ink ${small ? 'text-base leading-6' : 'text-lg leading-7'}`}>
        “{name}, {"it's"} time to {label ? `${label}.` : <Text className="text-ink-muted">…</Text>}”
      </Text>
    </View>
  );
}

/** One template: its icon, its name and when it plays, as a button. */
function TemplateTile({ template, selected, onPress }: { template: Template; selected: boolean; onPress: () => void }) {
  const { colors } = useTheme();
  const Icon = template.icon;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={`${template.title}: ${template.label}, ${formatClock(template.time)}`}
      onPress={onPress}
      className={`min-h-[84px] flex-1 items-start justify-between rounded-2xl p-2.5 active:opacity-80 ${
        selected ? 'bg-accent' : 'bg-surface'
      }`}
    >
      <Icon color={selected ? colors['on-accent'] : colors.ink} size={20} />
      <View className="gap-0.5">
        <Text className={`font-sans-semibold text-[13px] ${selected ? 'text-on-accent' : 'text-ink'}`}>
          {template.title}
        </Text>
        <Text className={`font-sans text-[11px] ${selected ? 'text-on-accent' : 'text-ink-muted'}`}>
          {spokenClock(template.time)}
        </Text>
      </View>
    </Pressable>
  );
}

/** A setting on its own line: what it is, a line of meta, and its control. */
function OptionRow({ title, meta, trailing }: { title: string; meta?: string; trailing?: React.ReactNode }) {
  return (
    <View className="flex-row items-center gap-3 rounded-2xl bg-surface px-3.5 py-3">
      <View className="flex-1 gap-0.5">
        <Text className="font-sans-semibold text-[15px] text-ink">{title}</Text>
        {meta ? <Text className="font-sans text-[13px] text-ink-muted">{meta}</Text> : null}
      </View>
      {trailing}
    </View>
  );
}

/** The next few weeks as a strip of days to pick one from. Today is marked by weight. */
export function DateStrip({
  today,
  value,
  onChange,
  count,
}: {
  today: string;
  value: string;
  onChange: (date: string) => void;
  count: number;
}) {
  const dates = Array.from({ length: count }, (_, i) => addDays(today, i));
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerClassName="gap-2">
      {dates.map((d) => {
        const selected = d === value;
        return (
          <Pressable
            key={d}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            accessibilityLabel={`${relativeDay(d, today)}, ${dayMonth(d)}`}
            onPress={() => onChange(d)}
            className={`h-16 w-12 items-center justify-center gap-0.5 rounded-xl active:opacity-80 ${
              selected ? 'bg-accent' : 'bg-surface'
            }`}
          >
            <Text className={`font-sans text-[11px] ${selected ? 'text-on-accent' : 'text-ink-muted'}`}>
              {d === today ? 'Today' : dayName(d)}
            </Text>
            <Text
              className={`text-base ${selected ? 'font-sans-bold text-on-accent' : d === today ? 'font-sans-bold text-ink' : 'font-sans text-ink'}`}
            >
              {Number(d.slice(8, 10))}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

/** Monday to Sunday as seven round toggles. */
function DayPicker({ value, onChange }: { value: number[]; onChange: (days: number[]) => void }) {
  return (
    <View className="flex-row justify-between">
      {DAY_LETTERS.map((letter, i) => {
        const day = i + 1;
        const on = value.includes(day);
        return (
          <Pressable
            key={day}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: on }}
            accessibilityLabel={DAY_NAMES[i]}
            onPress={() => onChange(on ? value.filter((d) => d !== day) : [...value, day].sort())}
            className={`size-11 items-center justify-center rounded-full active:opacity-80 ${
              on ? 'bg-accent' : 'border border-hairline'
            }`}
          >
            <Text className={`font-sans-semibold text-sm ${on ? 'text-on-accent' : 'text-ink'}`}>{letter}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}
