-- Seed data, kept out of the migration so the schema can be applied without it.
-- Safe to re-run: every insert skips rows that already exist.
--
-- Demo household: resident Margaret, the real pillow `mum`, carer Sarah (fake 555-01xx number).
-- Test household: "Test User" owns the hypothetical pillow `test-pillow`. Automated tests only
-- ever touch this one, so they never send a command to the real device.

-- Demo household -----------------------------------------------------------------------------

insert into residents (id, full_name, preferred_name)
values ('00000000-0000-0000-0000-000000000001', 'Margaret Test', 'Margaret')
on conflict do nothing;

insert into pillows (id, resident_id, location_label)
values ('mum', '00000000-0000-0000-0000-000000000001', 'Bedroom')
on conflict do nothing;

insert into contacts (id, full_name, phone, sms_consent)
values ('00000000-0000-0000-0000-000000000002', 'Sarah Test', '+15555550100', true)
on conflict (id) do update set sms_consent = excluded.sms_consent;  -- Guardian blocks SMS without it

insert into resident_contacts (resident_id, contact_id, relationship, role, priority)
values ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002',
        'daughter', 'owner', 1)
on conflict do nothing;

insert into pillow_state (pillow_id, head_on) values ('mum', false)
on conflict do nothing;

-- One reminder in each mode: she confirms her tablets; the dog walk is only announced.
insert into reminders (resident_id, label, kind, time_of_day, confirm)
select '00000000-0000-0000-0000-000000000001', label, kind, time_of_day::time, confirm
from (values ('take your heart tablets', 'meds', '08:00', true),
             ('take Biscuit for his walk', 'custom', '16:00', false)) as r (label, kind, time_of_day, confirm)
where not exists (select 1 from reminders where resident_id = '00000000-0000-0000-0000-000000000001');

-- Test household -----------------------------------------------------------------------------

insert into residents (id, full_name, preferred_name)
values ('00000000-0000-0000-0000-000000000011', 'Test Resident', 'Tess')
on conflict do nothing;

insert into pillows (id, resident_id, location_label)
values ('test-pillow', '00000000-0000-0000-0000-000000000011', 'Test bench')
on conflict do nothing;

insert into contacts (id, full_name, phone, sms_consent)
values ('00000000-0000-0000-0000-000000000012', 'Test User', '+15555550199', true)
on conflict (id) do update set sms_consent = excluded.sms_consent;

insert into resident_contacts (resident_id, contact_id, relationship, role, priority)
values ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000012',
        'tester', 'owner', 1)
on conflict do nothing;

insert into pillow_state (pillow_id, head_on) values ('test-pillow', false)
on conflict do nothing;
