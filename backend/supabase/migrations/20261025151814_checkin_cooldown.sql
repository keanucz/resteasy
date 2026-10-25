-- Demo: once the pillow has checked on her, it waits this long before checking again, so it doesn't
-- keep asking "Are you alright?" while she is up. The app's alert debug sets it to 0 (ask every time).
alter table residents
    add column checkin_cooldown_min integer not null default 10
        check (checkin_cooldown_min between 0 and 60);
