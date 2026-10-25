-- Four weeks for Margaret's pillow (`mum`) on top of demo_week.sql: the 21 nights before that week
-- (8 to 28 nights ago), plus restless spells and a cold room inside the week, so the app's month
-- and night charts have plenty to show. Written relative to today in her timezone; running it again
-- replaces what it made (events tagged data.seed = 'demo_month', and its incidents and reminders).
-- Run demo_readings.sql afterwards so the minute readings follow the new nights.
--
-- The story: most nights one short bathroom trip, every third night two. Restless every other
-- night. Three long trips: 11 and 24 nights ago she didn't answer and Sarah was alerted, 17 nights
-- ago she told the check-in she was fine. Cold rooms 9, 20 and 6 nights ago, a warm one 14 nights
-- ago, and 22 nights ago she pressed the family button.
--
-- Run: Supabase SQL editor, or the Supabase MCP's execute_sql.

create or replace function pg_temp.at(nights_ago int, t time) returns timestamptz language sql stable as $$
    -- A night starts on the evening `nights_ago` days before today; times before noon are the morning after.
    select ((now() at time zone 'America/Los_Angeles')::date - nights_ago
            + case when t < time '12:00' then 1 else 0 end + t) at time zone 'America/Los_Angeles'
$$;

-- A steady 0..n-1 number per night, so each night differs but a re-run gives the same month.
create or replace function pg_temp.jitter(n int, salt text, m int) returns int language sql immutable as $$
    select abs(hashtext(salt || n)) % m
$$;

-- Clear the previous run ----------------------------------------------------------------------

delete from events where pillow_id = 'mum' and data->>'seed' = 'demo_month';
delete from notifications where incident_id in (
    select id from incidents where pillow_id = 'mum' and opened_at >= pg_temp.at(28, '12:00')
      and (opened_at < pg_temp.at(7, '12:00') or kind <> 'no_return'));
delete from agent_log where pillow_id = 'mum' and args->>'seed' = 'demo_month';
delete from incidents where pillow_id = 'mum' and opened_at >= pg_temp.at(28, '12:00')
    and (opened_at < pg_temp.at(7, '12:00') or kind <> 'no_return');
delete from reminder_occurrences
    where reminder_id in (select r.id from reminders r join pillows p on p.resident_id = r.resident_id
                          where p.id = 'mum')
      and due_at >= pg_temp.at(28, '12:00') and due_at < pg_temp.at(7, '12:00');

-- The 21 nights -------------------------------------------------------------------------------

drop table if exists pg_temp.nights;
create temp table nights as
select n,
       time '22:00' + make_interval(mins => pg_temp.jitter(n, 'lay', 40)) as lay_down,
       time '22:00' + make_interval(mins => pg_temp.jitter(n, 'lay', 40) + 18 + pg_temp.jitter(n, 'sleep', 14)) as asleep,
       time '06:40' + make_interval(mins => pg_temp.jitter(n, 'up', 45)) as got_up
from generate_series(8, 28) as n;

drop table if exists pg_temp.trips;
create temp table trips as
select n, time '01:30' + make_interval(mins => pg_temp.jitter(n, 'trip', 140)) as left_at,
       case when n in (11, 17, 24) then 25 + pg_temp.jitter(n, 'long', 10) else 5 + pg_temp.jitter(n, 'len', 6) end
           as trip_min
from nights
union all
select n, time '04:15' + make_interval(mins => pg_temp.jitter(n, 'trip2', 30)), 6 + pg_temp.jitter(n, 'len2', 4)
from nights where n % 3 = 0;

drop table if exists pg_temp.restless;
create temp table restless as
select n, time '23:45' + make_interval(mins => pg_temp.jitter(n, 'rest', 50)) as from_t,
       time '23:45' + make_interval(mins => pg_temp.jitter(n, 'rest', 50) + 15 + pg_temp.jitter(n, 'restlen', 25)) as to_t
from generate_series(1, 28) as n
where n % 2 = 0 and n <> 6  -- night 6 already has one from demo_week
union all
select n, time '05:20', time '05:20' + make_interval(mins => 12 + pg_temp.jitter(n, 'dawn', 15))
from generate_series(8, 28) as n where n % 5 = 0;

insert into events (pillow_id, event_type, device_ts, data)
select 'mum', e.kind, e.ts, e.data || '{"seed": "demo_month"}'::jsonb from (
    select 'lay_down' as kind, pg_temp.at(n, lay_down) as ts, '{"watching": true}'::jsonb as data from nights
    union all select 'asleep', pg_temp.at(n, asleep), '{"quiet_min": 15}' from nights
    union all select 'got_up', pg_temp.at(n, got_up), '{}' from nights
    union all select 'restless', pg_temp.at(n, from_t), '{"motion_avg": 0.39}' from restless
    union all select 'settled', pg_temp.at(n, to_t), '{"motion_avg": 0.07}' from restless
    union all select 'bed_exit', pg_temp.at(n, left_at), jsonb_build_object('left_at', to_char(left_at, 'HH24:MI'))
        from trips
    union all select 'bed_return', pg_temp.at(n, left_at) + make_interval(mins => trip_min),
        jsonb_build_object('trip_min', trip_min) from trips
    union all select 'no_return', pg_temp.at(n, left_at) + interval '20 minutes', '{"away_min": 20, "round": 1}'
        from trips where trip_min >= 20
    union all select 'checkin_timeout', pg_temp.at(n, left_at) + interval '23 minutes', '{}'
        from trips where trip_min >= 20 and n in (11, 24)
    union all select 'family_ack', pg_temp.at(n, left_at) + interval '24 minutes', '{"contact": "Sarah"}'
        from trips where trip_min >= 20 and n in (11, 24)
    union all select 'checkin_result', pg_temp.at(n, left_at) + interval '21 minutes',
        '{"escalate": false, "reason": "she said she was letting the cat in"}'
        from trips where trip_min >= 20 and n = 17
    union all select 'family_button', pg_temp.at(22, '04:05'), '{}'
) as e;

-- Alerts ------------------------------------------------------------------------------------

with alert as (
    select t.n, pg_temp.at(t.n, t.left_at) as left_ts, t.trip_min from trips t where t.trip_min >= 20 and t.n in (11, 24)
), opened as (
    insert into incidents (pillow_id, kind, status, step, opened_at, acked_by, acked_at, resolved_at, summary)
    select 'mum', 'no_return', 'resolved', 2, left_ts + interval '23 minutes', '00000000-0000-0000-0000-000000000002',
           left_ts + interval '24 minutes', left_ts + make_interval(mins => trip_min),
           'Up at ' || ltrim(to_char(left_ts at time zone 'America/Los_Angeles', 'FMHH12:MI am'), '0')
           || ' and didn''t answer the check-in. Sarah was on it a minute later; back in bed at '
           || ltrim(to_char((left_ts + make_interval(mins => trip_min)) at time zone 'America/Los_Angeles', 'FMHH12:MI am'), '0') || '.'
    from alert
    returning id, opened_at
)
insert into notifications (incident_id, contact_id, channel, status, created_at)
select o.id, '00000000-0000-0000-0000-000000000002', ch.channel, 'delivered', o.opened_at + ch.after
from opened o cross join (values ('app', interval '0 minutes'), ('sms', interval '2 minutes')) as ch (channel, after);

insert into incidents (pillow_id, kind, status, step, opened_at, acked_by, acked_at, resolved_at, summary) values
    ('mum', 'room_cold', 'resolved', 1, pg_temp.at(9, '03:50'), null, null, pg_temp.at(9, '05:20'),
     'The bedroom dropped to 15.5' || chr(176) || 'C at 3:50 am. The heating came on and it was back above 17' || chr(176) || 'C by 5:20.'),
    ('mum', 'room_cold', 'resolved', 1, pg_temp.at(20, '04:30'), null, null, pg_temp.at(20, '06:00'),
     'A cold snap: the bedroom fell to 15.5' || chr(176) || 'C at 4:30 am and warmed again by 6:00.'),
    ('mum', 'room_cold', 'resolved', 1, pg_temp.at(6, '04:20'), null, null, pg_temp.at(6, '05:40'),
     'The bedroom dropped to 15.5' || chr(176) || 'C at 4:20 am. It was back above 17' || chr(176) || 'C by 5:40.'),
    ('mum', 'room_hot', 'resolved', 1, pg_temp.at(14, '01:10'), null, null, pg_temp.at(14, '02:40'),
     'A warm night: the bedroom reached 26' || chr(176) || 'C around 1:30 am. The pillow suggested opening a window.'),
    ('mum', 'distress', 'resolved', 1, pg_temp.at(22, '04:05'), '00000000-0000-0000-0000-000000000002',
     pg_temp.at(22, '04:08'), pg_temp.at(22, '04:25'),
     'Margaret pressed the family button. Sarah answered within 3 minutes; she had a bad dream and wanted to hear a voice.');

insert into agent_log (ts, pillow_id, agent, intent, tool, args, guardian)
select pg_temp.at(l.n, l.t::time), 'mum', l.agent, l.intent, l.tool, l.args || '{"seed": "demo_month"}'::jsonb, 'allowed'
from (values
    (22, '04:05', 'night_watch', 'family button pressed, call Sarah', 'notify', '{"contact": "Sarah", "channel": "call"}'::jsonb),
    (22, '04:08', 'family_app', 'Sarah is on it', 'ack', '{"contact": "Sarah"}'),
    (14, '01:12', 'comfort', 'room is warm, suggest a window', 'speak', '{"line": "It''s warm in here, Margaret. Shall we open a window?"}'),
    (9, '03:52', 'comfort', 'room is cold, suggest the heating', 'speak', '{"line": "It''s getting chilly. The heating is coming on."}')
) as l (n, t, agent, intent, tool, args);

-- Reminders over the 21 nights: tablets taken, except two mornings ----------------------------

insert into reminder_occurrences (reminder_id, due_at, status, attempts, last_asked_at, answered_at, reply)
select r.id, due, status, attempts, due + interval '10 minutes' * (attempts - 1),
       case when status = 'done' then due + interval '2 minutes' end,
       case when status = 'done' then 'Yes, I''ve taken them.' end
from reminders r
join pillows p on p.resident_id = r.resident_id and p.id = 'mum'
cross join lateral (
    select ((now() at time zone 'America/Los_Angeles')::date - d + r.time_of_day) at time zone 'America/Los_Angeles' as due,
           case when not r.confirm then 'announced' when d in (12, 19) then 'missed' else 'done' end as status,
           case when r.confirm and d in (12, 19, 15) then 2 else 1 end as attempts
    from generate_series(8, 28) as d
) as o;

select count(*) filter (where data->>'seed' = 'demo_month') as month_events,
       count(*) filter (where event_type = 'lay_down') as nights
from events where pillow_id = 'mum';
