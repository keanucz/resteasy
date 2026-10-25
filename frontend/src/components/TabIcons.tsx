import type { ColorValue } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

type IconProps = { color: ColorValue; size?: number };

/** A crescent moon: the Tonight tab. Drawn at a 1.8 stroke to sit with Figtree's weight. */
export function MoonIcon({ color, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
    </Svg>
  );
}

/** Two sliders: the Settings tab. */
export function SlidersIcon({ color, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M4 8h16M4 16h16" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
      <Circle cx={9} cy={8} r={2.4} fill={color} />
      <Circle cx={15} cy={16} r={2.4} fill={color} />
    </Svg>
  );
}

/** A capsule: a medicine reminder. */
export function PillIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d="M10.5 20.5 3.5 13.5a4.95 4.95 0 0 1 7-7l7 7a4.95 4.95 0 0 1-7 7Z"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <Path d="M7 10l7 7" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

/** A handset: a reminder to call someone. */
export function PhoneIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d="M5 4h3.5l1.5 4.5-2 1.5a11 11 0 0 0 6 6l1.5-2 4.5 1.5V19a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

/** A bell: any other reminder. */
export function BellIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
      <Circle cx={12} cy={20.5} r={1.2} fill={color} />
    </Svg>
  );
}

/** A page of a calendar with two rings and one day marked: the Reminders tab. */
export function CalendarIcon({ color, size = 24 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d="M5.5 5.5h13a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2Z"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <Path d="M3.5 10h17M8 3.5v3.5M16 3.5v3.5" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
      <Circle cx={15.5} cy={15} r={1.8} fill={color} />
    </Svg>
  );
}

/** A plus: add something. */
export function PlusIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M12 5v14M5 12h14" stroke={color} strokeWidth={2.2} strokeLinecap="round" />
    </Svg>
  );
}

/** A chevron pointing left or right: previous and next. */
export function ChevronIcon({ color, size = 20, left = false }: IconProps & { left?: boolean }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d={left ? 'M15 6l-6 6 6 6' : 'M9 6l6 6-6 6'}
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

/** A tick: it went well. */
export function CheckIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M5 12.5l4.5 4.5L19 7.5" stroke={color} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

/** A glass of water. */
export function GlassIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d="M6 4h12l-1.5 15.2a2 2 0 0 1-2 1.8h-5a2 2 0 0 1-2-1.8L6 4Z"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <Path d="M7 10.5c2.5-1.2 7.5 1.2 10 0" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

/** A triangle: play a voice. */
export function PlayIcon({ color, size = 18 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z" fill={color} />
    </Svg>
  );
}

/** A rounded square: stop what is playing or recording. */
export function StopIcon({ color, size = 18 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M8 6h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" fill={color} />
    </Svg>
  );
}

/** A microphone: record a voice. */
export function MicIcon({ color, size = 20 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path d="M12 3.5a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0v-5a3 3 0 0 1 3-3Z" stroke={color} strokeWidth={1.8} />
      <Path d="M6 11.5a6 6 0 0 0 12 0M12 17.5v3" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}
