-- Settings > Alerts: whether this person hears about restless spells (a gentle notice in the app,
-- never a text or a call). On by default, like the other alert switches.
alter table contacts add column if not exists restless_alerts boolean not null default true;

-- The app hears a restless spell (and every other night event) as it is written, not at the next
-- state change. Events are a few a night per pillow; RLS still limits each login to its household.
do $$
begin
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'events') then
    alter publication supabase_realtime add table events;
  end if;
end $$;
