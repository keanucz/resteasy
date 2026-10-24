-- One pillow only: glow_presence lit the second (kid) pillow, which no longer exists.

alter table commands drop constraint commands_cmd_check;
alter table commands add constraint commands_cmd_check
    check (cmd in ('set_light', 'pulse', 'vibrate', 'fan', 'stop_all'));
