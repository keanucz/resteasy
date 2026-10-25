-- Second step of 20261025010000: drop the old (reminder_id, due_at) slot key, so a 'remind' and a
-- 'consent' occurrence can share a due time. (reminder_id, due_at, purpose) is the key from now on.
--
-- Apply only once every running backend has the purpose-aware code (OCCURRENCE_KEY with `purpose`):
-- an older backend upserts on (reminder_id, due_at) and fails without this constraint.

alter table reminder_occurrences drop constraint reminder_occurrences_reminder_id_due_at_key;
