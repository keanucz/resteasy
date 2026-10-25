"""Fixed values for turning device state reports into the per-minute sensor history."""

# Seconds per `readings` row: the app's night charts draw one point per minute
READING_PERIOD_S = 60

# Device seconds between rewrites of the current minute's row, so the app's chart follows it live
# (a report arrives every ~0.5 s; writing each one would be ~120 upserts a minute per pillow)
READINGS_FLUSH_S = 5

# Decimal places kept for averaged values (motion 0..1, temperature, loudness in dBFS)
READING_DECIMALS = 3
