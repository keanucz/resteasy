const { raw, modes, logo } = require('./src/constants/palette');

// Theme roles read CSS variables that ThemeRoot sets per colour scheme, so `bg-canvas` is night in
// dark mode and day in light mode, and opacity modifiers (`bg-accent/25`) still work.
const roles = Object.fromEntries(Object.keys(modes.dark).map((name) => [name, `rgb(var(--${name}) / <alpha-value>)`]));

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  // Class mode lets the app (and the style guide) switch scheme in code; it still starts from the system setting.
  darkMode: 'class',
  theme: {
    extend: {
      colors: { ...raw, ...logo, ...roles },
      // Native fonts have one family name per weight, so pick weight with the family class, not font-bold.
      fontFamily: {
        display: ['Literata_600SemiBold'],
        'display-italic': ['Literata_600SemiBold_Italic'],
        'display-regular': ['Literata_400Regular'],
        sans: ['Figtree_400Regular'],
        'sans-medium': ['Figtree_500Medium'],
        'sans-semibold': ['Figtree_600SemiBold'],
        'sans-bold': ['Figtree_700Bold'],
      },
      borderRadius: {
        card: '20px',
        field: '14px',
      },
    },
  },
  plugins: [],
};
