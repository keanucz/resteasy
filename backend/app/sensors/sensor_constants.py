"""Fixed values for turning device state reports into the per-minute sensor history."""

# Seconds per `readings` row: the app's night charts draw one point per minute
READING_PERIOD_S = 60

# Device seconds between rewrites of the current minute's row, so the app's chart follows it live
# (a report arrives every ~0.5 s; writing each one would be ~120 upserts a minute per pillow)
READINGS_FLUSH_S = 5

# Decimal places kept for averaged values (motion 0..1, temperature, loudness in dBFS)
READING_DECIMALS = 3

# POST /ping: a report this many seconds old or newer counts as the boards answering (the bridge
# posts every ~0.5 s, so a live pillow always has one)
PING_FRESH_S = 2
# How long a ping keeps re-reading the state for a fresh report before saying the pillow is silent
PING_WAIT_S = 4
# Seconds between those re-reads
PING_POLL_S = 0.5
# A report stamped this far in the future is a seeded row, not a board answering
PING_CLOCK_SKEW_S = 2
