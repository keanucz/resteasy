-- Pillow schema, first version (3NF).
--
-- People:  residents (the elderly person) <-> contacts (carers) is many-to-many through
--          resident_contacts, so one carer can watch several residents (two pillows, a ward)
--          and one resident can have several carers.
-- Devices: pillows belong to a resident; pillow_state holds the latest reading per pillow.
-- Night:   events (what happened), commands (what the pillow should do), incidents (an alert
--          and who acknowledged it), notifications (each SMS / call / push sent for an incident),
--          agent_log (every agent action and the Guardian's verdict).
--
-- All writes go through FastAPI with the secret key (bypasses RLS). The app's publishable key
-- may only SELECT the tables it shows, and never sees phone numbers.

-- People -------------------------------------------------------------------------------------

create table residents (
    id                  uuid primary key default gen_random_uuid(),
    full_name           text not null,
    preferred_name      text not null,                -- what alerts and the voice call them
    timezone            text not null default 'America/Los_Angeles',
    language            text not null default 'en',
    voice_id            text not null default '62ae83ad-4f6a-430b-af41-a9bede9286ca',  -- Cartesia
    quiet_start         time not null default '22:00',
    quiet_end           time not null default '07:00',
    checkin_timeout_min integer not null default 20 check (checkin_timeout_min between 1 and 120),
    step_wait_min       integer not null default 2 check (step_wait_min between 1 and 30),
    monitoring_paused   boolean not null default false,
    created_at          timestamptz not null default now()
);

create table contacts (
    id          uuid primary key default gen_random_uuid(),
    full_name   text not null,
    phone       text unique check (phone ~ '^\+[1-9][0-9]{6,14}$'),  -- E.164, for Twilio
    sms_consent boolean not null default false,                      -- opted in to texts
    on_call     boolean not null default true,
    quiet_start time,                                                -- null = always reachable
    quiet_end   time,
    created_at  timestamptz not null default now(),
    check ((quiet_start is null) = (quiet_end is null))
);

create table resident_contacts (
    resident_id  uuid not null references residents (id) on delete cascade,
    contact_id   uuid not null references contacts (id) on delete cascade,
    relationship text,                                               -- 'daughter', 'night nurse'
    role         text not null default 'contact' check (role in ('owner', 'contact')),
    priority     integer not null check (priority >= 1),             -- 1 = alerted first
    primary key (resident_id, contact_id),
    unique (resident_id, priority)
);

-- Devices ------------------------------------------------------------------------------------

create table pillows (
    id             text primary key,                                 -- pillow_id in CONTRACT.md
    resident_id    uuid references residents (id) on delete set null,
    location_label text,                                             -- 'Room 4, bed B'
    created_at     timestamptz not null default now()
);

create table pillow_state (
    pillow_id    text primary key references pillows (id) on delete cascade,
    device_ts    timestamptz,
    head_on      boolean,
    motion       real check (motion between 0 and 1),
    room_motion  boolean,
    light        real check (light between 0 and 1),
    temp_c       real,
    humidity     real check (humidity between 0 and 100),
    key_talk     boolean,
    key_fine     boolean,
    key_family   boolean,
    knob         smallint check (knob between 0 and 10),
    night_state  text not null default 'awake'
                 check (night_state in ('awake', 'in_bed', 'up', 'check_in', 'escalating')),
    state_since  timestamptz not null default now(),
    last_seen_at timestamptz not null default now()
);

-- Night --------------------------------------------------------------------------------------

create table events (
    id          bigint generated always as identity primary key,
    pillow_id   text not null references pillows (id) on delete cascade,
    event_type  text not null,                                       -- lay_down, bed_exit, ...
    device_ts   timestamptz not null,                                -- device or simulator clock
    received_at timestamptz not null default now(),
    data        jsonb not null default '{}'
);
create index events_pillow_type_ts on events (pillow_id, event_type, device_ts);

create table commands (
    id         bigint generated always as identity primary key,      -- the device polls after=id
    pillow_id  text not null references pillows (id) on delete cascade,
    cmd        text not null
               check (cmd in ('set_light', 'pulse', 'vibrate', 'fan', 'glow_presence', 'stop_all')),
    args       jsonb not null default '{}',
    source     text,                                                 -- which agent queued it
    created_at timestamptz not null default now()
);
create index commands_pillow_id on commands (pillow_id, id);

create table incidents (
    id          bigint generated always as identity primary key,
    pillow_id   text not null references pillows (id) on delete cascade,
    kind        text not null check (kind in ('no_return', 'distress', 'room_cold', 'room_hot')),
    status      text not null default 'open'
                check (status in ('open', 'acknowledged', 'resolved', 'cancelled')),
    step        integer not null default 0,                          -- escalation rung reached
    opened_at   timestamptz not null default now(),
    acked_by    uuid references contacts (id) on delete set null,
    acked_at    timestamptz,
    resolved_at timestamptz,
    summary     text,
    check ((acked_by is null) = (acked_at is null))
);
create index incidents_pillow_status on incidents (pillow_id, status);

create table notifications (
    id           bigint generated always as identity primary key,
    incident_id  bigint not null references incidents (id) on delete cascade,
    contact_id   uuid not null references contacts (id) on delete cascade,
    channel      text not null check (channel in ('app', 'push', 'sms', 'call')),
    status       text not null default 'queued'
                 check (status in ('queued', 'sent', 'delivered', 'failed')),
    provider_ref text,                                               -- Twilio message / call SID
    error        text,
    created_at   timestamptz not null default now()
);
create index notifications_incident on notifications (incident_id);

create table agent_log (
    id          bigint generated always as identity primary key,
    ts          timestamptz not null default now(),
    pillow_id   text not null references pillows (id) on delete cascade,
    incident_id bigint references incidents (id) on delete set null,
    agent       text not null,                                       -- 'night_watch', 'check_in'
    intent      text,
    tool        text,
    args        jsonb not null default '{}',
    guardian    text check (guardian in ('allowed', 'blocked')),
    reason      text
);
create index agent_log_pillow_ts on agent_log (pillow_id, ts);

-- Derived: one row per completed night trip (bed_exit paired with the next bed_return), so the
-- trip length is computed, never stored. The personal baseline reads from here.
create view night_trips with (security_invoker = true) as
select e.pillow_id,
       e.device_ts                                            as left_at,
       r.device_ts                                            as returned_at,
       extract(epoch from (r.device_ts - e.device_ts)) / 60.0 as trip_min
from events e
join lateral (
    select device_ts
    from events r
    where r.pillow_id = e.pillow_id
      and r.event_type = 'bed_return'
      and r.device_ts > e.device_ts
    order by r.device_ts
    limit 1
) r on true
where e.event_type = 'bed_exit'
  and not exists (
      select 1
      from events x
      where x.pillow_id = e.pillow_id
        and x.event_type = 'bed_exit'
        and x.device_ts > e.device_ts
        and x.device_ts < r.device_ts
  );

-- Access -------------------------------------------------------------------------------------

alter table residents         enable row level security;
alter table contacts          enable row level security;
alter table resident_contacts enable row level security;
alter table pillows           enable row level security;
alter table pillow_state      enable row level security;
alter table events            enable row level security;
alter table commands          enable row level security;
alter table incidents         enable row level security;
alter table notifications     enable row level security;
alter table agent_log         enable row level security;

-- The app reads these; contacts, notifications, events and commands stay backend-only.
create policy app_read on residents         for select to anon, authenticated using (true);
create policy app_read on pillows           for select to anon, authenticated using (true);
create policy app_read on pillow_state      for select to anon, authenticated using (true);
create policy app_read on incidents         for select to anon, authenticated using (true);
create policy app_read on agent_log         for select to anon, authenticated using (true);

alter publication supabase_realtime add table pillow_state, incidents, agent_log;
