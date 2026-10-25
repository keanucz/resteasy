-- Demo: every login that looks after someone may change their settings (voice, alerts, simulator),
-- not only the one who set up the pillow. Existing links become owners, and so do new joins.
update resident_contacts set role = 'owner' where role <> 'owner';
alter table resident_contacts alter column role set default 'owner';
