-- The family app's voice studio (Cartesia): how the pillow speaks, words it says her way, accent
-- copies of a voice, and one cached sample per voice.
--
-- residents.voice_speed / voice_volume / voice_emotion
--     How the pillow speaks to her, set by the owner. The bounds are Cartesia's for sonic-3; the
--     defaults are how it always spoke (0.85, normal volume, calm). The pillow reads them with the
--     voice (GET /api/pillows/{id}/voice).
-- residents.pronunciation_dict_id
--     Her Cartesia pronunciation dictionary, rebuilt from `pronunciations` on every change.
-- residents.voice_id default
--     Skylar, the voice the backend and the pillow already fall back to (it said Gemma).
-- voice_clones.kind / base_voice_id / accent
--     A row is a family clone ('clone') or a copy of a voice with another accent ('accent', made
--     by Cartesia's localize from base_voice_id). `accent` is Cartesia's accent id: the clone's
--     own accent when the family gave it, or the accent of the copy.
-- pronunciations
--     Words (names, places, medicines) and how to say them, as plain "sounds like" spelling or
--     Cartesia IPA in <<...>>. Anyone in her care circle adds; whoever added one, or the owner, removes.
-- Storage bucket voice-samples
--     One MP3 per voice saying a fixed line: `stock/<voice_id>.mp3` shared by everyone, and
--     `<resident_id>/<voice_id>.mp3` for her own voices. Public to read by link; only the backend
--     (secret key) writes, so app users get no write policy.

alter table residents
    alter column voice_id set default 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4',
    add column voice_speed numeric(3, 2) not null default 0.85 check (voice_speed between 0.6 and 1.5),
    add column voice_volume numeric(3, 2) not null default 1.0 check (voice_volume between 0.5 and 2.0),
    add column voice_emotion text not null default 'calm',
    add column pronunciation_dict_id text;

alter table voice_clones
    add column kind text not null default 'clone' check (kind in ('clone', 'accent')),
    add column base_voice_id text,
    add column accent text;

create table pronunciations (
    id          uuid primary key default gen_random_uuid(),
    resident_id uuid not null references residents (id) on delete cascade,
    word        text not null check (char_length(word) between 1 and 60),         -- "Margaret"
    sounds_like text not null check (char_length(sounds_like) between 1 and 120),  -- "MAR-gret"
    created_by  uuid references contacts (id) on delete set null,
    created_at  timestamptz not null default now()
);
create unique index pronunciations_resident_word on pronunciations (resident_id, lower(word));

-- Writes go through FastAPI with the secret key; the app may read them like voice_clones.
alter table pronunciations enable row level security;
create policy app_read on pronunciations for select to anon, authenticated using (true);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('voice-samples', 'voice-samples', true, 1048576, array['audio/mpeg'])
on conflict (id) do nothing;
