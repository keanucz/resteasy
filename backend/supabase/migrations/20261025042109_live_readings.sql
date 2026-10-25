-- Real sensor data from the bedside voice unit (Waveshare ESP32-S3: QMI8658 IMU, ES8311 mic).
-- sim/audio_bridge.py posts its IMU motion, mic loudness and the link it is on (BLE, hotspot or
-- USB) in POST /state; the backend keeps the latest in pillow_state and one row per minute in
-- readings. Loudness is a number the board computes: no audio ever reaches the database.

alter table pillow_state add column if not exists sound_db real check (sound_db between -120 and 0);
alter table pillow_state add column if not exists link text check (link in ('ble', 'hotspot', 'usb'));
alter table readings add column if not exists sound_db real check (sound_db between -120 and 0);

-- The app's night charts follow the current minute's row as the backend rewrites it
alter publication supabase_realtime add table readings;
