-- The app reads a pillow's events and readings straight from Supabase, so the week and the night
-- charts work without a backend round trip. Only a signed-in member of that pillow's household
-- (any contact linked to the resident) may read them.

create or replace function public.in_pillow_household(p_pillow text) returns boolean
language sql stable security definer set search_path = public as $$
    select exists (
        select 1
        from pillows p
        join resident_contacts rc on rc.resident_id = p.resident_id
        join contacts c on c.id = rc.contact_id
        where p.id = p_pillow and c.user_id = (select auth.uid())
    );
$$;

create policy app_read on events for select to authenticated using (public.in_pillow_household(pillow_id));

drop policy app_read on readings;
create policy app_read on readings for select to authenticated using (public.in_pillow_household(pillow_id));

create index if not exists events_pillow_ts on events (pillow_id, device_ts);
