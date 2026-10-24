-- Recurring reminders (the Routine agent): "take your heart tablets", "call Sarah", "walk the dog".
--
-- reminders:            what the owner set up in the family app, per resident.
-- reminder_occurrences: one row per reminder per due time, created by the backend's tick when the
--                       time passes; unique (reminder_id, due_at) so a slot is created once even
--                       across restarts or two ticks racing.
--
-- Occurrence status:
--   waiting   -> the time has passed; held until she is up for the day (never wakes her), or
--                waiting for the retry after "not yet" / no answer
--   due       -> buzzer queued, the laptop speaks it and reports the result
--   announced -> spoken (announce-only reminders)
--   done      -> she confirmed (confirm reminders)
--   missed    -> no confirmation after every try, or not delivered within 3 h

create table reminders (
    id          bigint generated always as identity primary key,
    resident_id uuid not null references residents (id) on delete cascade,
    label       text not null check (char_length(label) between 1 and 80),  -- "take your heart tablets"
    kind        text not null default 'custom' check (kind in ('meds', 'call', 'custom')),
    time_of_day time not null,                                               -- in the resident's timezone
    days        smallint[] not null default '{1,2,3,4,5,6,7}'                -- ISO weekdays, 1 = Monday
                check (cardinality(days) > 0 and days <@ '{1,2,3,4,5,6,7}'::smallint[]),
    confirm     boolean not null default false,                              -- ask her to confirm, retry
    active      boolean not null default true,
    created_at  timestamptz not null default now()
);
create index reminders_resident on reminders (resident_id);

create table reminder_occurrences (
    id            bigint generated always as identity primary key,
    reminder_id   bigint not null references reminders (id) on delete cascade,
    due_at        timestamptz not null,
    status        text not null default 'waiting'
                  check (status in ('waiting', 'due', 'announced', 'done', 'missed')),
    attempts      integer not null default 0,                                -- times she was asked
    last_asked_at timestamptz,
    answered_at   timestamptz,
    reply         text check (char_length(reply) <= 300),                    -- transcript, never audio
    unique (reminder_id, due_at)
);
create index reminder_occurrences_open on reminder_occurrences (status) where status in ('waiting', 'due');

-- The passive buzzer sounds before a reminder is spoken.
alter table commands drop constraint commands_cmd_check;
alter table commands add constraint commands_cmd_check
    check (cmd in ('set_light', 'pulse', 'vibrate', 'fan', 'buzz', 'stop_all'));

alter table reminders            enable row level security;
alter table reminder_occurrences enable row level security;
create policy app_read on reminders            for select to anon, authenticated using (true);
create policy app_read on reminder_occurrences for select to anon, authenticated using (true);

alter publication supabase_realtime add table reminders, reminder_occurrences;
