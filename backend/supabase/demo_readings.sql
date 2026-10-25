-- Minute-by-minute sensor readings for the demo pillows (`mum`, `demo-dad`), worked out from the
-- events already seeded by demo_week.sql and demo_account.sql, so the charts agree with the story:
--   head_on  true from lying down to getting up, except while out of bed
--   motion   calm while asleep, high in restless spells and around getting in or out, 0 off the pillow
--   temp_c   a bedroom cooling overnight and warming towards morning, with the cold-room dip
--   (and the same warm-room bump for room_hot incidents)
-- Also marks both pillows online (last_seen_at three days ahead), since no device is posting.
-- Needs migrations/20261024233000_readings.sql. Re-runnable: it replaces its own rows.
--
-- Run: Supabase SQL editor, or the Supabase MCP's execute_sql.

select setseed(0.42);

delete from readings where pillow_id in ('mum', 'demo-dad');

with nights as (
    -- Each lay_down and the first got_up after it.
    select l.pillow_id, l.device_ts as lay_down,
           (select min(g.device_ts) from events g
             where g.pillow_id = l.pillow_id and g.event_type = 'got_up' and g.device_ts > l.device_ts) as got_up
    from events l
    where l.pillow_id in ('mum', 'demo-dad') and l.event_type = 'lay_down'
), spells as (
    -- Out-of-bed trips and restless spells, each paired with the event that ends it.
    select s.pillow_id, s.event_type as kind, s.device_ts as started,
           (select min(e.device_ts) from events e
             where e.pillow_id = s.pillow_id and e.device_ts > s.device_ts
               and e.event_type = case s.event_type when 'bed_exit' then 'bed_return' else 'settled' end) as ended
    from events s
    where s.pillow_id in ('mum', 'demo-dad') and s.event_type in ('bed_exit', 'restless')
), minutes as (
    select n.pillow_id, n.lay_down, n.got_up, ts,
           extract(epoch from ts - n.lay_down) / 3600.0 as hours_in,
           extract(epoch from n.got_up - n.lay_down) / 3600.0 as night_hours,
           -- A steady per-night offset, so no two nights have the same temperature line.
           (abs(hashtext(n.pillow_id || n.lay_down::date)) % 100) / 100.0 - 0.5 as night_offset
    from nights n
    cross join lateral generate_series(n.lay_down - interval '45 minutes', n.got_up + interval '30 minutes',
                                       interval '1 minute') as ts
    where n.got_up is not null
), shaped as (
    select m.*,
           m.ts >= m.lay_down and m.ts < m.got_up
           and not exists (select 1 from spells s where s.pillow_id = m.pillow_id and s.kind = 'bed_exit'
                             and m.ts >= s.started and m.ts < s.ended) as head_on,
           exists (select 1 from spells s where s.pillow_id = m.pillow_id and s.kind = 'restless'
                     and m.ts >= s.started and m.ts < s.ended) as restless,
           -- Minutes from the nearest getting in or out of bed.
           least(abs(extract(epoch from m.ts - m.lay_down)), abs(extract(epoch from m.ts - m.got_up)),
                 coalesce((select min(least(abs(extract(epoch from m.ts - s.started)),
                                            abs(extract(epoch from m.ts - s.ended))))
                           from spells s where s.pillow_id = m.pillow_id and s.kind = 'bed_exit'), 1e9)) / 60.0
               as near_move_min,
           -- The cold-room incident: the minutes since it opened, while it was open.
           (select extract(epoch from m.ts - i.opened_at) / 60.0 from incidents i
             where i.pillow_id = m.pillow_id and i.kind = 'room_cold'
               and m.ts between i.opened_at - interval '40 minutes' and i.resolved_at limit 1) as cold_min,
           -- A warm-room incident, the same way.
           (select extract(epoch from m.ts - i.opened_at) / 60.0 from incidents i
             where i.pillow_id = m.pillow_id and i.kind = 'room_hot'
               and m.ts between i.opened_at - interval '40 minutes' and i.resolved_at limit 1) as hot_min
    from minutes m
)
insert into readings (pillow_id, ts, temp_c, head_on, motion)
select pillow_id, ts,
       round((case
           when cold_min is not null
               -- Falls to 15.5 C as the incident opens, then recovers over 90 minutes.
               then 15.5 + abs(cold_min) / 40.0 * case when cold_min < 0 then 3.0 else 1.6 end
           when hot_min is not null
               -- Climbs to 26 C as the incident opens, then cools over 90 minutes.
               then 26.0 - abs(hot_min) / 40.0 * case when hot_min < 0 then 5.0 else 2.4 end
           else 20.6 + night_offset
                -- Cools through the night, warms again over the last 90 minutes.
                - 2.3 * least(1, greatest(0, hours_in) / greatest(night_hours - 1.5, 1))
                + 1.1 * greatest(0, hours_in - (night_hours - 1.5)) / 1.5
       end + (random() - 0.5) * 0.12)::numeric, 1)::real,
       head_on,
       round((case
           when not head_on then 0
           when near_move_min < 4 then 0.45 + random() * 0.3
           when restless then 0.28 + random() * 0.32
           else 0.02 + random() * 0.05 + case when random() < 0.03 then 0.12 else 0 end
       end)::numeric, 3)::real
from shaped;

-- No device is posting for these pillows, so keep the app from calling them offline.
update pillow_state set last_seen_at = now() + interval '3 days' where pillow_id in ('mum', 'demo-dad');

select pillow_id, count(*) as readings, min(ts) as first, max(ts) as last,
       round(min(temp_c)::numeric, 1) as coldest, round(max(temp_c)::numeric, 1) as warmest
from readings where pillow_id in ('mum', 'demo-dad') group by pillow_id;

-- Two more of Dad's past alerts: a warm room (with the readings warmed to match) and a press of the
-- family button. Re-runnable: it removes its own incidents first.
delete from incidents where pillow_id = 'demo-dad' and kind in ('room_hot', 'distress');
delete from events where pillow_id = 'demo-dad' and event_type = 'family_button';

with n as (
  select device_ts as lay_down, row_number() over (order by device_ts desc) as k
  from events where pillow_id = 'demo-dad' and event_type = 'lay_down'
), hot as (
  insert into incidents (pillow_id, kind, status, step, opened_at, resolved_at, summary)
  select 'demo-dad', 'room_hot', 'resolved', 1, lay_down + interval '3 hours 10 minutes', lay_down + interval '4 hours 25 minutes',
         'Dad''s bedroom reached 26.1' || chr(176) || 'C. The pillow suggested opening a window, and it cooled within the hour.'
  from n where k = 2
  returning opened_at, resolved_at
), help as (
  insert into incidents (pillow_id, kind, status, step, opened_at, acked_by, acked_at, resolved_at, summary)
  select 'demo-dad', 'distress', 'resolved', 1, lay_down + interval '5 hours 2 minutes',
         '00000000-0000-0000-0000-0000000000d3', lay_down + interval '5 hours 6 minutes', lay_down + interval '5 hours 30 minutes',
         'Dad pressed the family button at the pillow. Ella answered within 4 minutes; he couldn''t find his glasses.'
  from n where k = 7
  returning opened_at
), button as (
  insert into events (pillow_id, event_type, device_ts, data)
  select 'demo-dad', 'family_button', opened_at, '{"seed":"demo_account"}'::jsonb from help
  returning 1
)
update readings r
set temp_c = round((24.0 + 2.1 * sin(pi() * extract(epoch from r.ts - (h.opened_at - interval '40 minutes'))
                    / extract(epoch from (h.resolved_at + interval '20 minutes') - (h.opened_at - interval '40 minutes'))))::numeric, 1)
from hot h
where r.pillow_id = 'demo-dad' and r.ts between h.opened_at - interval '40 minutes' and h.resolved_at + interval '20 minutes';
