/** Typed access to EXPO_PUBLIC_* variables. Read env vars here only, never inline elsewhere. */

const DEFAULT_API_URL = 'http://localhost:8000';

export const env = {
  apiUrl: process.env.EXPO_PUBLIC_API_URL ?? DEFAULT_API_URL,
  supabaseUrl: process.env.EXPO_PUBLIC_SUPABASE_URL ?? '',
  supabasePublishableKey: process.env.EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? '',
} as const;
