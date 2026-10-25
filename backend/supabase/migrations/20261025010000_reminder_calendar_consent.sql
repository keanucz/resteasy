-- Reminders from the family calendar: one-offs, skipped days, delivery channels, and her consent.
--
-- reminders:
--   on_date     set: a one-off on that date (her timezone), `days` is then ignored
--   skip_dates  dates a recurring reminder does not play (one occurrence dragged to another day)
--   channels    how it reaches her; only 'voice' is delivered today (SMS/email via Twilio later)
--   consent     nothing plays until she agrees, asked by the pillow itself:
--                 pending  -> asked by day, at most once a day (two tries), until she answers
--                 agreed   -> plays on schedule
--                 declined -> never plays; changing what or when asks her again
--               Rows from before this migration were set up before consent existed: 'agreed'.
--   consent_at  when she answered
--   created_by  the family member who set it up, named when the pillow asks her
--
-- reminder_occurrences.purpose: 'remind' (say the reminder) or 'consent' (ask whether she agrees).
-- A remind and a consent occurrence may share a due time, so the slot key gains `purpose`.
--
-- Additive, so a backend still on the old code keeps working: the old (reminder_id, due_at) key
-- stays for its upserts and is dropped by 20261025010500 once every backend has this code.

alter table reminders
    add column on_date    date,
    add column skip_dates date[] not null default '{}',
    add column channels   text[] not null default '{voice}'
               check (cardinality(channels) > 0 and channels <@ '{voice,sms,email}'::text[]),
    add column consent    text not null default 'agreed'
               check (consent in ('pending', 'agreed', 'declined')),
    add column consent_at timestamptz,
    add column created_by uuid references contacts (id) on delete set null;

-- Existing rows took 'agreed' above; every reminder made from now on waits for her answer.
alter table reminders alter column consent set default 'pending';

alter table reminder_occurrences
    add column purpose text not null default 'remind' check (purpose in ('remind', 'consent'));
alter table reminder_occurrences
    add constraint reminder_occurrences_reminder_id_due_at_purpose_key unique (reminder_id, due_at, purpose);
