-- Sensor history for the app's night charts. pillow_state keeps only the latest reading; this keeps
-- one row per pillow per minute: bedroom temperature, whether a head is on the pillow, and how much
-- the pillow moves (IMU, 0 to 1). The backend writes it from POST /state (at most once a minute).

create table readings (
    pillow_id text not null references pillows (id) on delete cascade,
    ts        timestamptz not null,
    temp_c    real,                                     -- null while the sensor isn't wired
    head_on   boolean,
    motion    real check (motion between 0 and 1),
    primary key (pillow_id, ts)
);

alter table readings enable row level security;
create policy app_read on readings for select to anon, authenticated using (true);
