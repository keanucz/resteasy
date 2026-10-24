---
name: Rest Easy
description: The family's window onto a parent's night, built to be read at 2 am.
colors:
  night: "#171537"
  dusk: "#2A2752"
  mist: "#EEEFF6"
  glow: "#9499E6"
  calm: "#9FD6C2"
  alert: "#E64C6B"
  night-muted: "#A39EAB"
  line: "#433F65"
  bone: "#3A3862"
  day: "#F5F6FE"
  day-card: "#FFFFFF"
  day-field: "#EBECF7"
  day-line: "#DCDDEF"
  day-muted: "#6C697E"
  day-bone: "#EBEBF0"
  glow-day: "#686CB5"
  glow-day-text: "#6266AF"
  state-asleep: "#9FD6C2"
  state-restless: "#E2A8F5"
  state-up: "#F4C46C"
  state-alert: "#FF9C94"
  state-offline: "#B8BAC6"
  state-asleep-day: "#0F7C66"
  state-restless-day: "#8E3BB3"
  state-up-day: "#A85C00"
  state-alert-day: "#C8202F"
  state-offline-day: "#5C6178"
  on-color: "#FFFFFF"
typography:
  display:
    fontFamily: "Literata_600SemiBold, Literata, Georgia, serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: "36px"
  headline:
    fontFamily: "Literata_600SemiBold, Literata, Georgia, serif"
    fontSize: "24px"
    fontWeight: 600
    lineHeight: "30px"
  status-word:
    fontFamily: "Literata_600SemiBold_Italic, Literata, Georgia, serif"
    fontWeight: 600
  title:
    fontFamily: "Literata_600SemiBold, Literata, Georgia, serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: "28px"
  motto:
    fontFamily: "Literata_400Regular, Literata, Georgia, serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: "28px"
  body:
    fontFamily: "Figtree_400Regular, Figtree, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: "24px"
  body-strong:
    fontFamily: "Figtree_600SemiBold, Figtree, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: "24px"
  meta:
    fontFamily: "Figtree_400Regular, Figtree, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "18px"
  label:
    fontFamily: "Figtree_600SemiBold, Figtree, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "16px"
  column-header:
    fontFamily: "Figtree_600SemiBold, Figtree, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.1em"
rounded:
  check: "6px"
  row: "8px"
  segment: "10px"
  button: "12px"
  field: "14px"
  tile: "16px"
  card: "20px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  gap: "10px"
  inset: "14px"
  md: "16px"
  card: "18px"
  gutter: "22px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.glow}"
    textColor: "{colors.night}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.button}"
    padding: "0 24px"
    height: "44px"
  button-primary-day:
    backgroundColor: "{colors.glow-day}"
    textColor: "{colors.on-color}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.button}"
    padding: "0 24px"
    height: "44px"
  button-secondary:
    backgroundColor: "#9499E640"
    textColor: "{colors.mist}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.button}"
    padding: "0 24px"
    height: "44px"
  button-alert:
    backgroundColor: "{colors.alert}"
    textColor: "{colors.on-color}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.button}"
    padding: "0 24px"
    height: "44px"
  button-ghost:
    textColor: "{colors.glow}"
    typography: "{typography.body-strong}"
    height: "44px"
  icon-button:
    backgroundColor: "{colors.dusk}"
    rounded: "{rounded.full}"
    size: "44px"
  text-field:
    backgroundColor: "{colors.dusk}"
    textColor: "{colors.mist}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "0 16px"
    height: "48px"
  text-field-day:
    backgroundColor: "{colors.day-field}"
    textColor: "{colors.night}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "0 16px"
    height: "48px"
  chip:
    textColor: "{colors.mist}"
    rounded: "{rounded.full}"
    padding: "0 14px"
    height: "32px"
  chip-selected:
    backgroundColor: "{colors.glow}"
    textColor: "{colors.night}"
    rounded: "{rounded.full}"
    padding: "0 14px"
    height: "32px"
  segmented-tabs:
    backgroundColor: "{colors.dusk}"
    rounded: "{rounded.segment}"
    padding: "3px"
  list-row:
    backgroundColor: "{colors.dusk}"
    textColor: "{colors.mist}"
    rounded: "{rounded.tile}"
    padding: "14px"
  stat-tile:
    backgroundColor: "{colors.dusk}"
    textColor: "{colors.mist}"
    rounded: "{rounded.tile}"
    padding: "14px"
  card:
    backgroundColor: "{colors.dusk}"
    textColor: "{colors.mist}"
    rounded: "{rounded.card}"
    padding: "18px"
  card-day:
    backgroundColor: "{colors.day-card}"
    textColor: "{colors.night}"
    rounded: "{rounded.card}"
    padding: "18px"
  checkbox-checked:
    backgroundColor: "{colors.calm}"
    textColor: "{colors.night}"
    rounded: "{rounded.check}"
    size: "22px"
---

# Design System: Rest Easy

<!-- This file RECORDS the shipped frontend; it does not redesign it. The source of truth is the code:
frontend/src/constants/palette.js (colours and theme roles), frontend/tailwind.config.js, frontend/src/constants/
sky.ts, motion.ts and frontend/src/components/. Where any generic design rule (Impeccable's slop list, platform
defaults) disagrees with this file or that code, this file and the code win. Change the code first, then re-run
/impeccable document. -->

## Overview

**Creative North Star: "The Night Light"**

Rest Easy is a small, steady glow in a dark room. It is there when you look and never glaring. The app is opened by an adult child at 2 am, half asleep, sometimes frightened, and every decision serves that moment: a dark-first canvas the eye can rest on, one sentence that says how Mum is, and colour that stays quiet until it means something. Calm is the default; clarity is the job; alarm is reserved for the one state that earns it.

The look is warm and nocturnal rather than clinical. A literary serif (Literata) speaks the headlines and the status, the way a note left on the bedside table would; a friendly sans (Figtree) carries everything you tap and scan. The top of the home screen is a sky in the state's own colours that arcs and fades into the page; below it, the furniture is flat, soft and tonal. There is room for quiet playfulness (the mascot, small kindnesses in copy and empty states) but never inside an alert.

Density is low on purpose. One focal sentence, a few facts, and the ways to act. If a screen needs a label to explain a state, the state was not said clearly enough.

**Key Characteristics:**
- Dark-first, with a fully designed Light mode; Dark is the default on every device.
- State said in words: a sentence with one italic key word in the state's colour. Never a pill.
- The sky carries the mood; the rest of the screen stays flat and tonal.
- Serif for what she is doing, sans for what you can do.
- Soft and sure controls: rounded, filled, borderless, a gentle press, nothing bounces.

## Colors

A dusk palette: deep indigo night, a lamp-like periwinkle accent, one mint for "all good" and one rose that only appears when she needs you.

### Primary
- **Glow** (#9499E6 on dark, Glow Day #686CB5 as a fill and #6266AF as text on light): the one accent. Primary buttons, selected chips, switch tracks, ghost links, the focused field border. It means "you can act here", never "something is wrong".

### Secondary
- **Calm** (#9FD6C2): "all good". Ticked checkboxes, the asleep state on dark, the in-bed bar of the night ribbon. Text on Calm is Night.

### Tertiary
- **Alert** (#E64C6B): escalation only. The alert button fill and the alert avatar. As text it is too dark on Night, so alert words use the lighter State Alert tone instead.

### Neutral
- **Night** (#171537): the dark canvas, and the text colour on Glow and Calm fills.
- **Dusk** (#2A2752): dark surfaces: cards, list rows, tiles, fields, dialogs, the segmented control.
- **Mist** (#EEEFF6): primary text on dark.
- **Night Muted** (#A39EAB): secondary text on dark (6.7:1 on Night, 5.3:1 on Dusk).
- **Line** (#433F65): hairlines and unselected chip borders on dark.
- **Day** (#F5F6FE), **Day Card** (#FFFFFF), **Day Field** (#EBECF7), **Day Line** (#DCDDEF), **Day Muted** (#6C697E): the same roles in Light mode, where Night becomes the text colour.
- **Bone** (#3A3862 dark, #EBEBF0 light): ghost-loading placeholders, the ink colour at about 10% over the surface.

### State colours
Each state has one hue, pale on dark and deep on light, every one at least 4.5:1 on its surface. They are used as text only: Asleep (#9FD6C2 / #0F7C66), Restless (#E2A8F5 / #8E3BB3), Up (#F4C46C / #A85C00), Alert (#FF9C94 / #C8202F), Offline (#B8BAC6 / #5C6178). Up is the amber complement of the indigo night; Restless is its analogous orchid.

### The sky
The home header and the login screen sit under a sky whose two-stop gradient is the state: Asleep #121C48 to #284A8E (Light #C6DEFA to #DCE8FB), Restless #26133D to #6A2D6C, Up #1F2150 to #3D3570 with an amber glow at the lower left, Alert #2C0F1E to #6E1E2C with a rose glow at the centre, Offline #24252E to #3A3C46. The headline's key word takes the sky's own ink (#B9C8FF, #E2A8F5, #FFD58A, #FF9C94, #B8BAC6 on dark).

### Named Rules
**The Theme Role Rule.** Screens use theme roles (canvas, surface, field, ink, ink-muted, hairline, accent, danger, state-*), never fixed hexes, so Light mode keeps working untouched.

**The Rose Means Now Rule.** Alert rose appears only when she needs you: the alert sky, the alert word, the alert button, the alert avatar. Never as decoration, never as an error tint for ordinary form mistakes beyond the error text itself.

**The One Glow Rule.** Glow is the only interactive accent. State colours are for words, never for buttons or fills.

## Typography

**Display Font:** Literata (with Georgia, serif)
**Body Font:** Figtree (with system-ui, sans-serif)

**Character:** Literata is a bookish, warm serif that sounds like a person; Figtree is round and friendly without being childish. Together they read as a letter from someone who sat up with her, set on controls that are easy to hit half asleep.

Native fonts ship one family per weight, so weight is chosen by family (Figtree_600SemiBold), not by a bold flag.

### Hierarchy
- **Display** (Literata 600, 30px, 36px): screen titles such as the app name on login.
- **Headline** (Literata 600, 24px, 30px): the status sentence, "Mum is asleep".
- **Status word** (Literata 600 italic, inherits size): the one key word of a status, in the state colour.
- **Title** (Literata 600, 20px, 28px): card headings such as "A quiet night", dialog titles at 18px.
- **Motto** (Literata 400, 18px): the tagline under the logo, in the sky's detail colour rather than muted grey.
- **Body** (Figtree 400, 16px, 24px): sentences, field values. Detail lines under the headline are 14px.
- **Body strong** (Figtree 600, 16px): button labels, list row titles, stat values at 20px.
- **Meta** (Figtree 400, 13px): row metadata, notification detail, times.
- **Label** (Figtree 600, 12px): field labels above inputs, sentence case.
- **Column header** (Figtree 600, 11px, 0.1em tracking, uppercase): table column headers only.

### Named Rules
**The Serif Speaks Rule.** Literata is for what she is doing and what the app is saying (status, headings, the motto). Anything you tap or scan is Figtree.

**The No Eyebrow Rule.** No small uppercase label above a heading. Uppercase tracking is reserved for table column headers.

## Layout

Single-column phone layout with a 16px side gutter (22px inside the sky header). Spacing runs on a 4px base with a few named steps: 8 inside tight groups, 10 between sibling cards and rows, 14 inside tiles and rows, 18 inside cards and dialogs, 24 to 32 between sections. Stat tiles sit two or three to a row with 10px gaps; everything else stacks.

The home screen is the sky header (status bar inset plus a 230px horizon plus a 52px fade) followed by the stats placed exactly where the fade ends. The login screen uses a taller sky (290px horizon) with the logo (a 1.5px hairline in the photo ring's neutral sets its navy badge apart from the same-coloured sky), name and tagline centred inside it and the email and password form pulled 24px up into the fade, so the fields sit near the middle of the screen: one primary button, and a ghost under it that swaps the form between logging in and creating an account. Content respects the safe area on every edge; the sky alone runs under the status bar.

**The Photo Stays Put Rule.** The photo ring is pinned left in the header; a long headline wraps beside it and never pushes it.

## Elevation & Depth

Flat, tonal layers. Depth comes from three tones (canvas, surface, field) rather than shadows: a Dusk card on a Night canvas is already lifted. The single shadow in the system belongs to notification cards, which float over other content. Dialogs sit on a 50% black scrim instead of a shadow.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`): notification cards only.

### Named Rules
**The Flat By Default Rule.** Surfaces are flat at rest. A shadow means "this is on top of something", never "this is important". No glows as depth; the sky's glows belong to the sky.

## Shapes

Soft, generous rounding that grows with the size of the object: 6px checkboxes and skeleton bones, 8px table row bands, 10px segmented control, 12px buttons, 14px fields, 16px rows and tiles, 20px cards and dialogs, full circles for avatars, switches, chips and the photo ring. No borders on filled surfaces; borders appear only on unselected chips and checkboxes (1 to 1.5px, Line) and on a focused or failing field.

The sky's bottom edge is the system's signature silhouette: a -cosh(1.5x) arch rising 15% of the horizon, fading out over 52px with a smoothstep, so the header melts into the page instead of ending in a line.

## Components

### Buttons
Soft and sure: filled, rounded, borderless, sentence-case semibold labels, and a press that shrinks to 98% and springs back with no overshoot.
- **Shape:** gently rounded (12px), 44px tall, 24px side padding, full width in forms and dialogs.
- **Primary:** Glow fill with Night label on dark; Glow Day fill with white label on light. One per view.
- **Secondary:** Glow at 25% with the ink colour as label.
- **Alert:** Alert rose fill with a white label, only for an urgent or destructive confirm. White on #E64C6B is 3.7:1, below 4.5:1 for 16px text; a known trade-off to revisit.
- **Ghost:** no fill, accent-text label; the quiet way out under a primary ("Not now").
- **States:** pressed 80% opacity plus the press scale; disabled 40% opacity; loading swaps the label for a spinner in the label colour at the same size, so the button never resizes.
- **Icon button:** a 44px Dusk circle.

### Chips
- **Style:** 32px tall pills used only as filters the user taps: unselected is a 1px Line outline with ink text; selected is a Glow fill with Night text.
- **State:** never used to label a status. A chip that labels a state is a status pill and is banned.

### Cards / Containers
- **Corner Style:** 20px for cards and dialogs, 16px for list rows, stat tiles and summary cards.
- **Background:** Dusk on dark, white on light.
- **Shadow Strategy:** none (see Elevation), except notification cards.
- **Border:** none.
- **Internal Padding:** 18px cards, 14px rows and tiles.

### Inputs / Fields
- **Style:** filled, 48px tall, 14px radius, 16px side padding, Dusk (dark) or Day Field (light), label above in 12px semibold muted text.
- **Focus:** a 1.5px Glow border appears; nothing else moves.
- **Error / Disabled:** the border turns Alert and a 12px message in the danger-text colour appears under the field. On the login form the line under the password is always reserved, so the buttons never jump: it holds the error (fading in over 220ms) or, while creating an account, the password rule in muted text.

### Navigation
A native stack with no visible header on the app's own screens; the system edge-swipe back stays alive. A tab bar is not built yet; when it arrives it holds two to five sections, never actions.

### Selection
- **Switch:** the platform switch with a Glow track when on, Line when off, white thumb.
- **Segmented tabs:** a Dusk track (10px radius, 3px padding); the selected segment is an ink-at-15% band (8px radius) with ink text, unselected segments are muted.
- **Checkbox:** a 22px square with 6px corners, 1.5px Line border; checked fills Calm with a Night tick.

### Status headline (signature)
"Mum is *asleep*": the status as one Literata sentence, with only the key word in italic and the state's colour. It replaces every badge, pill and dot a monitoring app would normally use. The detail line under it is plain 14px text ("In bed since 10:42 pm").

### Sky header (signature)
The state's two-stop gradient with its glow, seeded stars only while she is in bed (asleep, restless) and only in Dark mode, the photo ring and the status headline, ending in the arched fade. State changes cross-fade the sky: 700ms for calm changes, 250ms into alert, slow again when an alert resolves.

### Photo ring
Her photo or initials in a 1.5px neutral ring. The ring only speaks when it matters: 3px rose when she needs you, a dotted 2px ring when the pillow is offline.

### Night ribbon
The night from 10 pm to 7 am as one 18px rounded track: a solid Calm bar while in bed, a hatched orchid bar while restless, a thinner amber or rose bar when up or alerting, a hatched muted bar when unknown, and a 2px line for now.

### Ghost loading
Skeleton bones in the Bone tone that keep the real container and breathe together in one slow pulse (opacity 1 to 0.55, 900ms each way, sine easing). They appear only after a 200ms wait and stay at least 400ms; under reduced motion they are static. A button's own submit uses its spinner instead.

## Do's and Don'ts

### Do:
- **Do** say the state in a sentence with one italic key word in the state colour ("Mum is *up*").
- **Do** use theme roles (canvas, surface, field, ink, ink-muted, hairline, accent, state-*) so Light mode keeps working.
- **Do** keep one Glow primary button per view and put the quiet way out (ghost) under it.
- **Do** keep text at 4.5:1 or better in both modes; state colours are already tuned for it.
- **Do** keep motion short and eased out (90 to 320ms), with the sky crossfade as the one slow, signature moment, and honour reduced motion.
- **Do** keep the sky's photo and headline in fixed positions whatever the copy length.

### Don't:
- **Don't** use status pills, badges, chips or dots that label a state, in any restyled form.
- **Don't** show stars when she is up, alerting or offline, or in Light mode.
- **Don't** use Alert rose for decoration or anything that is not escalation.
- **Don't** add shadows to cards or glow halos as depth; the system is flat and tonal.
- **Don't** put small uppercase eyebrow labels above headings.
- **Don't** bounce, wiggle, pulse a status, or count numbers up.
- **Don't** call the modes day and night in the interface; they are Light and Dark.
