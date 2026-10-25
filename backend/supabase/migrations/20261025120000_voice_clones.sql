-- Voices cloned in the family app (Cartesia), one row per clone, each for one resident.
--
-- A clone is made from a short recording of someone she knows, with that person's consent, and is
-- offered next to the stock voices (backend/app/core/voice_constants.py) only for her. residents.voice_id
-- may hold a stock voice or one of these; removing a clone puts her back on the default voice.
--
-- voice_id   Cartesia's id for the cloned voice (the backend removes it there too)
-- created_by the family member who recorded it, named in the app's voice picker

create table voice_clones (
    voice_id    text primary key,
    resident_id uuid not null references residents (id) on delete cascade,
    name        text not null check (char_length(name) between 1 and 40),  -- "Sarah"
    created_by  uuid references contacts (id) on delete set null,
    created_at  timestamptz not null default now()
);
create index voice_clones_resident on voice_clones (resident_id);

-- Writes go through FastAPI with the secret key; the app may read them like the reminders.
alter table voice_clones enable row level security;
create policy app_read on voice_clones for select to anon, authenticated using (true);
