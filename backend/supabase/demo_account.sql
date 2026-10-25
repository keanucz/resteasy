-- A dummy household for Szymon's own app login (szymon@example.com), so the app has a full
-- fortnight to show without touching Margaret's pillow (`mum`), which the real hardware posts to.
--
-- Resident "Dad" (Arthur Bennett) on pillow `demo-dad`, owned by Szymon's login, with his sister
-- Ella as second contact. 14 nights before today in his timezone, written relative to today so it
-- can be re-run on any day; running it again replaces everything it made.
--
-- The pillow has no device, so its state is frozen "in bed" and last_seen_at is set three days
-- ahead; otherwise the app would call it offline two minutes after this runs.
--
-- Run: Supabase SQL editor, or the Supabase MCP's execute_sql.

create or replace function pg_temp.at(nights_ago int, t time) returns timestamptz language sql stable as $$
    -- A night starts on the evening `nights_ago` days before today; times before noon are the morning after.
    select ((now() at time zone 'America/Los_Angeles')::date - nights_ago
            + case when t < time '12:00' then 1 else 0 end + t) at time zone 'America/Los_Angeles'
$$;

create or replace function pg_temp.day(days_ago int, t time) returns timestamptz language sql stable as $$
    -- `t` on the calendar day `days_ago` days before today (0 = today).
    select ((now() at time zone 'America/Los_Angeles')::date - days_ago + t) at time zone 'America/Los_Angeles'
$$;

-- Clear the previous run ----------------------------------------------------------------------

delete from notifications where incident_id in (select id from incidents where pillow_id = 'demo-dad');
delete from incidents where pillow_id = 'demo-dad';
delete from agent_log where pillow_id = 'demo-dad';
delete from events where pillow_id = 'demo-dad';
delete from commands where pillow_id = 'demo-dad';
delete from pillow_state where pillow_id = 'demo-dad';
delete from pillows where id = 'demo-dad';
delete from residents where id = '00000000-0000-0000-0000-0000000000d1';  -- reminders cascade
delete from resident_contacts where contact_id in ('00000000-0000-0000-0000-0000000000d2',
                                                   '00000000-0000-0000-0000-0000000000d3');
delete from contacts where id in ('00000000-0000-0000-0000-0000000000d2', '00000000-0000-0000-0000-0000000000d3');

-- The household -------------------------------------------------------------------------------

insert into residents (id, full_name, preferred_name, timezone, voice_id)
values ('00000000-0000-0000-0000-0000000000d1', 'Arthur Bennett', 'Dad', 'America/Los_Angeles',
        'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4');

insert into contacts (id, full_name, user_id)
select '00000000-0000-0000-0000-0000000000d2', 'Szymon', id from auth.users where email = 'szymon@example.com';
insert into contacts (id, full_name) values ('00000000-0000-0000-0000-0000000000d3', 'Ella');

insert into resident_contacts (resident_id, contact_id, relationship, role, priority) values
    ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-0000000000d2', 'son', 'owner', 1),
    ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-0000000000d3', 'daughter', 'contact', 2);
-- Szymon also looks in on Margaret (not her owner, and with no phone, so nobody is texted), so the app
-- has two people to switch between. The alert simulator only plays on pillows he owns.
insert into resident_contacts (resident_id, contact_id, relationship, role, priority) values
    ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-0000000000d2', 'grandson', 'contact', 5);

insert into pillows (id, resident_id, location_label)
values ('demo-dad', '00000000-0000-0000-0000-0000000000d1', 'Bedroom');

insert into pillow_state (pillow_id, device_ts, head_on, motion, room_motion, light, temp_c, humidity,
                          night_state, state_since, last_seen_at)
values ('demo-dad', now(), true, 0.04, false, 0.02, 19.5, 46,
        'in_bed', pg_temp.at(1, '22:12'), now() + interval '3 days');

-- Fourteen nights -----------------------------------------------------------------------------

drop table if exists pg_temp.nights;
create temp table nights (n int, lay_down time, asleep time, got_up time);
insert into nights values
    (1, '22:12', '22:35', '06:58'), (2, '22:30', '22:52', '07:05'), (3, '22:05', '22:31', '06:47'),
    (4, '22:41', '23:10', '07:15'), (5, '22:18', '22:40', '06:55'), (6, '22:25', '22:49', '07:02'),
    (7, '22:09', '22:33', '06:50'), (8, '22:36', '23:01', '07:11'), (9, '22:15', '22:38', '06:59'),
    (10, '22:22', '22:44', '07:03'), (11, '22:03', '22:29', '06:45'), (12, '22:47', '23:14', '07:20'),
    (13, '22:20', '22:41', '06:57'), (14, '22:28', '22:50', '07:06');

-- Bathroom trips: when he got up and how long until he was back in bed.
drop table if exists pg_temp.trips;
create temp table trips (n int, left_at time, trip_min int);
insert into trips values
    (1, '02:40', 7), (2, '01:55', 6), (2, '04:30', 8), (3, '03:22', 34), (4, '02:10', 9),
    (5, '03:48', 7), (6, '01:30', 8), (6, '04:12', 26), (7, '02:58', 6), (8, '03:15', 10),
    (9, '02:05', 33), (10, '03:40', 7), (11, '02:22', 8), (11, '05:05', 6), (13, '03:01', 9),
    (14, '02:35', 7);

-- Restless spells while in bed.
drop table if exists pg_temp.restless;
create temp table restless (n int, from_t time, to_t time);
insert into restless values (2, '00:20', '00:45'), (4, '01:05', '01:40'), (8, '23:50', '00:15'),
                            (12, '00:30', '01:10'), (12, '04:00', '04:25');

insert into events (pillow_id, event_type, device_ts, data)
select 'demo-dad', e.kind, e.ts, e.data from (
    select 'lay_down' as kind, pg_temp.at(n, lay_down) as ts, '{"watching": true}'::jsonb as data from nights
    union all select 'asleep', pg_temp.at(n, asleep), '{"quiet_min": 15}' from nights
    union all select 'got_up', pg_temp.at(n, got_up), '{}' from nights
    union all select 'restless', pg_temp.at(n, from_t), '{"motion_avg": 0.38}' from restless
    union all select 'settled', pg_temp.at(n, to_t), '{"motion_avg": 0.07}' from restless
    union all select 'bed_exit', pg_temp.at(n, left_at), jsonb_build_object('left_at', to_char(left_at, 'HH24:MI'))
        from trips
    union all select 'bed_return', pg_temp.at(n, left_at) + make_interval(mins => trip_min),
        jsonb_build_object('trip_min', trip_min) from trips
    -- Long trips: the pillow asked after 20 min.
    union all select 'no_return', pg_temp.at(n, left_at) + interval '20 minutes', '{"away_min": 20, "round": 1}'
        from trips where trip_min >= 20
) as e;

-- 6 nights ago he answered the check-in: he was making tea.
insert into events (pillow_id, event_type, device_ts, data) values
    ('demo-dad', 'checkin_result', pg_temp.at(6, '04:33'), '{"escalate": false, "reason": "he said he was making tea"}');

-- 3 and 9 nights ago he didn't answer, and family were alerted.
insert into events (pillow_id, event_type, device_ts, data) values
    ('demo-dad', 'checkin_timeout', pg_temp.at(3, '03:45'), '{}'),
    ('demo-dad', 'family_ack', pg_temp.at(3, '03:49'), '{"contact": "Szymon"}'),
    ('demo-dad', 'checkin_timeout', pg_temp.at(9, '02:28'), '{}'),
    ('demo-dad', 'family_ack', pg_temp.at(9, '02:34'), '{"contact": "Ella"}');

with alert (n, opened, acked, resolved, by_contact, by_name, summary) as (values
    (3, time '03:45', time '03:49', time '03:56', uuid '00000000-0000-0000-0000-0000000000d2', 'Szymon',
     'Up at 3:22 am and didn''t answer the check-in. Szymon was on it at 3:49; back in bed at 3:56.'),
    (9, time '02:28', time '02:34', time '02:38', uuid '00000000-0000-0000-0000-0000000000d3', 'Ella',
     'Up at 2:05 am and didn''t answer the check-in. Ella was on it at 2:34; back in bed at 2:38.')
), opened as (
    insert into incidents (pillow_id, kind, status, step, opened_at, acked_by, acked_at, resolved_at, summary)
    select 'demo-dad', 'no_return', 'resolved', 2, pg_temp.at(n, opened), by_contact, pg_temp.at(n, acked),
           pg_temp.at(n, resolved), summary
    from alert
    returning id, opened_at
)
insert into notifications (incident_id, contact_id, channel, status, created_at)
select o.id, c.id, ch.channel, 'delivered', o.opened_at + ch.after
from opened o
cross join (values ('app', interval '0 minutes'), ('sms', interval '2 minutes')) as ch (channel, after)
cross join (values (uuid '00000000-0000-0000-0000-0000000000d2'), (uuid '00000000-0000-0000-0000-0000000000d3')) as c (id);

-- A cold night: the room dropped below 16 degrees.
insert into incidents (pillow_id, kind, status, step, opened_at, resolved_at, summary)
values ('demo-dad', 'room_cold', 'resolved', 1, pg_temp.at(5, '04:10'), pg_temp.at(5, '05:40'),
        'The bedroom dropped to 15.5 C at 4:10 am. It was back above 17 C by 5:40.');

insert into agent_log (ts, pillow_id, agent, intent, tool, args, guardian)
select pg_temp.at(l.n, l.t::time), 'demo-dad', l.agent, l.intent, l.tool, l.args, 'allowed'
from (values
    (3, '03:42', 'check_in', 'ask if he is alright', 'speak', '{"line": "Arthur, are you alright?"}'::jsonb),
    (3, '03:45', 'night_watch', 'no answer, alert family', 'notify', '{"contact": "Szymon", "channel": "app"}'),
    (3, '03:49', 'family_app', 'Szymon is on it', 'ack', '{"contact": "Szymon"}'),
    (3, '03:56', 'night_watch', 'back in bed, stand down', null, '{}'),
    (6, '04:32', 'check_in', 'ask if he is alright', 'speak', '{"line": "Arthur, are you alright?"}'),
    (6, '04:33', 'check_in', 'he is fine, stand down', null, '{"reply": "Just making tea."}'),
    (9, '02:25', 'check_in', 'ask if he is alright', 'speak', '{"line": "Arthur, are you alright?"}'),
    (9, '02:28', 'night_watch', 'no answer, alert family', 'notify', '{"contact": "Szymon", "channel": "app"}'),
    (9, '02:34', 'family_app', 'Ella is on it', 'ack', '{"contact": "Ella"}'),
    (9, '02:38', 'night_watch', 'back in bed, stand down', null, '{}')
) as l (n, t, agent, intent, tool, args);

-- Reminders, with how each went over the fortnight and so far today ---------------------------

insert into reminders (resident_id, label, kind, time_of_day, confirm) values
    ('00000000-0000-0000-0000-0000000000d1', 'take your blood pressure tablet', 'meds', '08:00', true),
    ('00000000-0000-0000-0000-0000000000d1', 'call Ella', 'call', '18:30', false),
    ('00000000-0000-0000-0000-0000000000d1', 'take your evening tablets', 'meds', '21:00', true);

insert into reminder_occurrences (reminder_id, due_at, status, attempts, last_asked_at, answered_at, reply)
select r.id, due, status, attempts,
       due + interval '10 minutes' * (attempts - 1),
       case when status = 'done' then due + interval '10 minutes' * (attempts - 1) + interval '1 minute' end,
       case when status = 'done' then 'Yes, done.' end
from reminders r
cross join lateral (
    select d, pg_temp.day(d, r.time_of_day) as due,
           case when not r.confirm then 'announced'
                when (d, r.time_of_day) in ((4, time '08:00'), (10, time '21:00')) then 'missed'
                else 'done' end as status,
           case when (d, r.time_of_day) in ((4, time '08:00'), (10, time '21:00'), (7, time '08:00')) then 2
                else 1 end as attempts
    from generate_series(0, 14) as d
) as o
where r.resident_id = '00000000-0000-0000-0000-0000000000d1'
  and due < now();  -- only the ones that have fallen due

select (select count(*) from events where pillow_id = 'demo-dad') as events,
       (select count(*) from incidents where pillow_id = 'demo-dad') as incidents,
       (select count(*) from notifications n join incidents i on i.id = n.incident_id where i.pillow_id = 'demo-dad') as notifications,
       (select count(*) from agent_log where pillow_id = 'demo-dad') as agent_log,
       (select count(*) from reminder_occurrences o join reminders r on r.id = o.reminder_id
         where r.resident_id = '00000000-0000-0000-0000-0000000000d1') as occurrences,
       (select count(*) from contacts where user_id = (select id from auth.users where email = 'szymon@example.com')) as linked;
