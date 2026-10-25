import type { Session } from '@supabase/supabase-js';
import { useEffect, useState } from 'react';

import { supabase } from '@/services/supabase/client';

/** The current auth session, kept live; `loading` is true until the stored session has been read. */
export function useSession(): { session: Session | null; loading: boolean } {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      // The stored session is trusted until its token expires, so ask the server whether it still
      // stands: a login revoked or deleted in Supabase drops back to the login screen straight away.
      let stored = data.session;
      if (stored) {
        const { error } = await supabase.auth.getUser();
        if (error?.status === 401 || error?.status === 403) {
          await supabase.auth.signOut({ scope: 'local' });
          stored = null;
        }
      }
      setSession(stored);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  return { session, loading };
}
