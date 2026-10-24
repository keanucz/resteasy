/**
 * The app's single Supabase client, using the publishable key (RLS limits what it can read).
 * The session is persisted in the app's sandboxed storage: expo-sqlite's localStorage on the phone,
 * the browser's own localStorage on the web.
 */

import 'react-native-url-polyfill/auto';
import 'expo-sqlite/localStorage/install';

import { createClient } from '@supabase/supabase-js';
import { AppState, Platform } from 'react-native';

import { env } from '@/config/env';

export const supabase = createClient(env.supabaseUrl, env.supabasePublishableKey, {
  auth: {
    storage: globalThis.localStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

// Native apps only refresh the token while in the foreground; browsers handle this themselves.
if (Platform.OS !== 'web') {
  AppState.addEventListener('change', (state) => {
    if (state === 'active') {
      supabase.auth.startAutoRefresh();
    } else {
      supabase.auth.stopAutoRefresh();
    }
  });
}
