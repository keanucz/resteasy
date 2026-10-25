-- The words a queued notification carries, so the sender (app/notify) can text or speak them.
-- Older rows have none; the sender falls back to the incident's summary.
alter table notifications add column if not exists message text;
