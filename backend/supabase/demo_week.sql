-- The demo's "hardcoded week" for Margaret's pillow (`mum`): the 7 nights before today, written
-- relative to today in her timezone, so it can be re-run on any day. It deletes its own rows
-- first (events tagged data.seed = 'demo_week', and the incidents and reminder occurrences
-- inside that week), so running it twice gives the same week. Nothing today or later is touched.
--
-- A normal week: 1-2 short bathroom trips a night (6-9 min). Two nights stand out:
--   4 nights ago: up at 3:12, no answer to the check-in, Sarah alerted and on it at 3:39.
--   2 nights ago: a 25 minute trip; she told the check-in she was fine.
--
-- Run: Supabase SQL editor, or the Supabase MCP's execute_sql.

create function pg_temp.at(nights_ago int, t time) returns timestamptz language sql stable as $$
    -- A night starts on the evening `nights_ago` days before today; times before noon are the morning after.
    select ((now() at time zone 'America/Los_Angeles')::date - nights_ago
            + case when t < time '12:00' then 1 else 0 end + t) at time zone 'America/Los_Angeles'
$$;

create function pg_temp.week_start() returns timestamptz language sql stable as $$
    select ((now() at time zone 'America/Los_Angeles')::date - 7 + time '00:00') at time zone 'America/Los_Angeles'
$$;

create function pg_temp.today_start() returns timestamptz language sql stable as $$
    select ((now() at time zone 'America/Los_Angeles')::date + time '00:00') at time zone 'America/Los_Angeles'
$$;

-- Clear the previous run --------------------------------------------------------------------

delete from events where pillow_id = 'mum' and data ->> 'seed' = 'demo_week';
delete from agent_log where pillow_id = 'mum' and args ->> 'seed' = 'demo_week';
delete from incidents
    where pillow_id = 'mum' and opened_at >= pg_temp.week_start() and opened_at < pg_temp.today_start();
delete from reminder_occurrences
    where reminder_id in (select r.id from reminders r join pillows p on p.resident_id = r.resident_id
                          where p.id = 'mum')
      and due_at >= pg_temp.week_start() and due_at < pg_temp.today_start();

-- The nights --------------------------------------------------------------------------------

insert into events (pillow_id, event_type, device_ts, data)
select 'mum', e.kind, pg_temp.at(e.n, e.t::time), e.data || '{"seed": "demo_week"}'::jsonb
from (values
    (7, 'lay_down',   '22:20', '{"watching": true}'::jsonb),
    (7, 'asleep',     '22:41', '{"quiet_min": 15}'),
    (7, 'bed_exit',   '02:14', '{"left_at": "02:14"}'),
    (7, 'bed_return', '02:21', '{"trip_min": 7}'),
    (7, 'got_up',     '06:52', '{}'),

    (6, 'lay_down',   '22:05', '{"watching": true}'),
    (6, 'asleep',     '22:30', '{"quiet_min": 15}'),
    (6, 'restless',   '00:40', '{"motion_avg": 0.41}'),
    (6, 'settled',    '00:58', '{"motion_avg": 0.08}'),
    (6, 'bed_exit',   '03:05', '{"left_at": "03:05"}'),
    (6, 'bed_return', '03:13', '{"trip_min": 8}'),
    (6, 'got_up',     '07:05', '{}'),

    (5, 'lay_down',   '22:35', '{"watching": true}'),
    (5, 'asleep',     '23:02', '{"quiet_min": 15}'),
    (5, 'bed_exit',   '01:48', '{"left_at": "01:48"}'),
    (5, 'bed_return', '01:54', '{"trip_min": 6}'),
    (5, 'bed_exit',   '04:40', '{"left_at": "04:40"}'),
    (5, 'bed_return', '04:49', '{"trip_min": 9}'),
    (5, 'got_up',     '07:10', '{}'),

    (4, 'lay_down',        '22:12', '{"watching": true}'),
    (4, 'asleep',          '22:33', '{"quiet_min": 15}'),
    (4, 'bed_exit',        '03:12', '{"left_at": "03:12"}'),
    (4, 'no_return',       '03:32', '{"away_min": 20, "round": 1}'),
    (4, 'checkin_timeout', '03:35', '{}'),
    (4, 'family_ack',      '03:39', '{"contact": "Sarah"}'),
    (4, 'bed_return',      '03:43', '{"trip_min": 31}'),
    (4, 'got_up',          '07:20', '{}'),

    (3, 'lay_down',   '22:25', '{"watching": true}'),
    (3, 'asleep',     '22:44', '{"quiet_min": 15}'),
    (3, 'bed_exit',   '02:30', '{"left_at": "02:30"}'),
    (3, 'bed_return', '02:37', '{"trip_min": 7}'),
    (3, 'got_up',     '06:58', '{}'),

    (2, 'lay_down',       '22:18', '{"watching": true}'),
    (2, 'asleep',         '22:39', '{"quiet_min": 15}'),
    (2, 'bed_exit',       '01:55', '{"left_at": "01:55"}'),
    (2, 'no_return',      '02:15', '{"away_min": 20, "round": 1}'),
    (2, 'checkin_result', '02:16', '{"escalate": false, "reason": "she said she was fine"}'),
    (2, 'bed_return',     '02:20', '{"trip_min": 25}'),
    (2, 'got_up',         '07:02', '{}'),

    (1, 'lay_down',   '22:10', '{"watching": true}'),
    (1, 'asleep',     '22:29', '{"quiet_min": 15}'),
    (1, 'bed_exit',   '03:02', '{"left_at": "03:02"}'),
    (1, 'bed_return', '03:09', '{"trip_min": 7}'),
    (1, 'got_up',     '06:55', '{}')
) as e (n, kind, t, data);

-- The one escalation: no answer at 3:35, Sarah on it at 3:39, back in bed at 3:43 ------------

with incident as (
    insert into incidents (pillow_id, kind, status, step, opened_at, acked_by, acked_at, resolved_at, summary)
    values ('mum', 'no_return', 'resolved', 2, pg_temp.at(4, '03:35'), '00000000-0000-0000-0000-000000000002',
            pg_temp.at(4, '03:39'), pg_temp.at(4, '03:43'),
            'Up at 3:12 am and didn''t answer the check-in. Sarah was on it at 3:39; back in bed at 3:43.')
    returning id
), alerts as (
    insert into notifications (incident_id, contact_id, channel, status, created_at)
    select incident.id, '00000000-0000-0000-0000-000000000002', n.channel, 'delivered', pg_temp.at(4, n.t::time)
    from incident, (values ('app', '03:35'), ('sms', '03:37')) as n (channel, t)
)
insert into agent_log (ts, pillow_id, incident_id, agent, intent, tool, args, guardian)
select pg_temp.at(4, l.t::time), 'mum', incident.id, l.agent, l.intent, l.tool,
       l.args || '{"seed": "demo_week"}'::jsonb, 'allowed'
from incident, (values
    ('03:32', 'check_in',     'ask if she is alright',        'speak',  '{"line": "Margaret, are you alright?"}'::jsonb),
    ('03:35', 'night_watch',  'no answer, alert family',      'notify', '{"contact": "Sarah", "channel": "app"}'),
    ('03:37', 'night_watch',  'still no answer, text Sarah',  'notify', '{"contact": "Sarah", "channel": "sms"}'),
    ('03:39', 'family_app',   'Sarah is on it',               'ack',    '{"contact": "Sarah"}'),
    ('03:43', 'night_watch',  'back in bed, stand down',      null,     '{}')
) as l (t, agent, intent, tool, args);

-- Reminders: tablets taken every morning except one; Biscuit's walk announced each afternoon -----

insert into reminder_occurrences (reminder_id, due_at, status, attempts, last_asked_at, answered_at, reply)
select r.id, pg_temp.at(d.n, r.time_of_day) - interval '1 day' * (case when r.time_of_day < time '12:00' then 1 else 0 end),
       d.status, d.attempts,
       pg_temp.at(d.n, r.time_of_day) - interval '1 day' * (case when r.time_of_day < time '12:00' then 1 else 0 end)
           + interval '10 minutes' * (d.attempts - 1),
       case when d.status = 'done'
            then pg_temp.at(d.n, r.time_of_day) - interval '1 day' * (case when r.time_of_day < time '12:00' then 1 else 0 end)
                 + interval '2 minutes' end,
       case when d.status = 'done' then 'Yes, I''ve taken them.' end
from reminders r
join pillows p on p.resident_id = r.resident_id and p.id = 'mum'
cross join lateral (
    select n,
           case when not r.confirm then 'announced' when n = 3 then 'missed' else 'done' end as status,
           case when r.confirm and n = 3 then 2 else 1 end as attempts
    from generate_series(1, 7) as n
) as d;
