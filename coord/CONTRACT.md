# Device contract (pillow ↔ cloud)

The one interface every lane builds against. The real ESP32 and the fake pillow (`sim/pillow_sim.py`)
both speak it, so agents and backend never care which one is plugged in. Change it only with a
`decision` message on the bus and a note in the CONTEXT.md decisions log.

Transport for the weekend: plain HTTP JSON. The device pushes state and polls for commands
(an ESP32 handles that more reliably than holding a WebSocket open). Szymon owns the server side;
the backend stores them in Supabase but the HTTP endpoints and message shapes stay as below.

## 1. Device → cloud: state (about 2 per second, and on any change)

`POST /api/pillows/{pillow_id}/state`

```json
{
  "pillow_id": "mum",            // one pillow only; string, stable per device
  "ts": 1792815000.25,           // real Unix seconds. Boards have no clock: the serial bridge
                                 // stamps the laptop's time (sim: simulated clock)
  "head_on": true,               // touch sensor / IMU says a head is on the pillow
  "motion": 0.12,                // restlessness 0..1, IMU movement averaged over the last 10 s
  "room_motion": false,          // PIR on the nightstand
  "light": 0.03,                 // photoresistor 0 (dark) .. 1 (bright)
  "temp_c": 19.5,                // DHT11, null if not wired
  "humidity": 48,                // DHT11, null if not wired
  "keys": {"talk": false, "fine": false, "family": false},  // keypad, true while held
  "knob": 5                      // 0..10, null if not wired
}
```

Unknown or missing sensors are `null`, never omitted. The server derives events from changes;
the device does not decide what anything means.

## 2. Cloud-side events (derived by the state machine, not sent by the device)

| Event | Rule (defaults; thresholds live in config, not in the LLM) |
|---|---|
| `lay_down` | `head_on` false → true for ≥ 5 s |
| `bed_exit` | `head_on` true → false for ≥ 30 s, between 22:00 and 07:00 |
| `bed_return` | `head_on` true again after a `bed_exit` |
| `no_return` | `bed_exit` and no `bed_return` within `checkin_timeout_min` (20) |
| `restless` | `head_on` and `motion` > 0.35 averaged over 10 min |
| `asleep` | `head_on` and `motion` < 0.08 for 15 min |
| `key_talk` / `key_fine` / `key_family` | key goes false → true |

## 3. Cloud → device: commands

`GET /api/pillows/{pillow_id}/commands?after={last_command_id}` → `[]` or a list, oldest first.
The device polls every 500 ms, runs each command, then remembers its `id`.

```json
{"id": 41, "cmd": "set_light", "args": {"brightness_pct": 20, "color": "warm", "fade_s": 3}}
```

| `cmd` | `args` | Device does |
|---|---|---|
| `set_light` | `brightness_pct` 0–100, `color` `warm`/`amber`/`off`, `fade_s` 0–60 | LEDs / path light |
| `pulse` | `start_bpm`, `end_bpm` (4–14), `duration_min` (1–30) | motor + glow breathing ramp |
| `vibrate` | `pattern` `tap`/`double`/`long`, `repeat` 1–5 | motor |
| `fan` | `speed_pct` 0–100 | kit fan motor |
| `stop_all` | none | everything off |

Speech and audio (`say`, `play_audio`) play on the base laptop/speaker, not the ESP32, so they are
not device commands. Guardian caps brightness, volume and intensity before a command is queued.

## 4. Pillows

| `pillow_id` | Who | Hardware |
|---|---|---|
| `mum` | the resident (older adult living alone) | booth ESP32 + sensors (`firmware/pillow/`) |

There is no second pillow. The adult child / carer uses only the family app: live status card,
in-app alerts and an "I'm on it" button (see the decisions log in `coord/CONTEXT.md`).
