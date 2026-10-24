-- Scope the app's reads to the signed-in carer's own households.
--
-- Until now every app_read policy was `to anon, authenticated using (true)`: anyone holding the
-- publishable key (it ships inside the app) could read every resident, pillow and alert. Logins
-- now exist (contacts.user_id -> auth.users), so a row is visible only to an authenticated user
-- whose contact row looks after that resident. Anonymous reads return nothing.
--
-- FastAPI and the agents use the secret key, which bypasses RLS, so nothing server-side changes.
-- contacts and resident_contacts stay unreadable from the app (phone numbers); the lookup runs in
-- security definer functions instead.

create function public.my_resident_ids()
returns setof uuid
language sql
stable
security definer
set search_path = ''
as $$
    select rc.resident_id
    from public.resident_contacts rc
    join public.contacts c on c.id = rc.contact_id
    where c.user_id = (select auth.uid())
$$;

create function public.my_pillow_ids()
returns setof text
language sql
stable
security definer
set search_path = ''
as $$
    select p.id
    from public.pillows p
    where p.resident_id in (select public.my_resident_ids())
$$;

revoke execute on function public.my_resident_ids() from public, anon;
revoke execute on function public.my_pillow_ids() from public, anon;
grant execute on function public.my_resident_ids() to authenticated;
grant execute on function public.my_pillow_ids() to authenticated;

drop policy app_read on residents;
drop policy app_read on pillows;
drop policy app_read on pillow_state;
drop policy app_read on incidents;
drop policy app_read on agent_log;
drop policy app_read on reminders;
drop policy app_read on reminder_occurrences;

create policy app_read on residents for select to authenticated
    using (id in (select public.my_resident_ids()));
create policy app_read on pillows for select to authenticated
    using (resident_id in (select public.my_resident_ids()));
create policy app_read on pillow_state for select to authenticated
    using (pillow_id in (select public.my_pillow_ids()));
create policy app_read on incidents for select to authenticated
    using (pillow_id in (select public.my_pillow_ids()));
create policy app_read on agent_log for select to authenticated
    using (pillow_id in (select public.my_pillow_ids()));
create policy app_read on reminders for select to authenticated
    using (resident_id in (select public.my_resident_ids()));
create policy app_read on reminder_occurrences for select to authenticated
    using (reminder_id in (select r.id from reminders r where r.resident_id in (select public.my_resident_ids())));
