-- Nights a family member can't be called first, told to their Fetch.ai family agent ("I'm in Denver
-- Thu to Sun") or set in the app. One row per stretch, from_date (first night) to until_date (last
-- night), inclusive. Each evening the coordinator asks every family agent, which answers from here,
-- and puts that contact off call those nights; Night Watch still alerts everyone in the end.
--
-- Per contact, not per resident: someone away is away for everyone they look after.

create table contact_away (
    id          bigint generated always as identity primary key,
    contact_id  uuid not null references contacts (id) on delete cascade,
    from_date   date not null,
    until_date  date not null,
    note        text not null default 'away' check (char_length(note) between 1 and 80),  -- "in Denver"
    created_at  timestamptz not null default now(),
    check (until_date >= from_date)
);
create index contact_away_contact on contact_away (contact_id, until_date);

-- When someone is away from home is private: only FastAPI (the secret key) reads or writes it, and
-- each family member sees only their own dates through the API. No policies on purpose.
alter table contact_away enable row level security;
