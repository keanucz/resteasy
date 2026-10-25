# pillow_uno: the switch plate on the Arduino Uno R3 (retired)

**Superseded (Sat 24 Oct):** the plate is wired straight to the N16R8 pillow node (`../pillow_node/`),
which prints the same line itself. Kept for reference and for the bench bridge (`sim/uno_bridge.py`).

The head sensor is a pressure plate: two cardboard sheets faced with aluminium foil, foam or cloth
between them. A head pressing them together closes the circuit. The Uno reads it and prints one
JSON line per 500 ms; it never decides what a reading means (that is the server's job, per
`coord/CONTRACT.md`: `lay_down` after 5 s, `bed_exit` after 10 s, sleep rules in
`backend/app/agents/sleep_events.py`).

## Wiring

| From | To | Note |
|---|---|---|
| plate side 1 | Uno pin 2 | `INPUT_PULLUP`: pressed reads LOW |
| plate side 2 | Uno GND | |
| Uno pin 13 | LED, 1 kΩ, GND | on = head on the pillow (handy for the demo) |
| Uno pin 1 (TX) | 1 kΩ, then Waveshare GPIO44 (U0RXD) | plus 2 kΩ from GPIO44 to GND: the S3 is not 5 V tolerant |
| Uno GND | Waveshare GND | shared ground, or nothing is readable |

Leave the Waveshare's GPIO43 unwired. Power the Uno from USB (a power bank or the laptop); the
Waveshare voice unit in the pillow forwards every Uno line as `UNO <line>` over its link
(`firmware/README.md`, "The Uno").

## Line format (9600 baud, under 200 chars)

```
{"head_on":1,"motion":null,"room_motion":null,"light":null,"temp_c":null,"humidity":null,"fine":0,"talk":0,"family":0}
```

Only `head_on` is real today; the others are `null` as the contract asks, and the keys are 0 so the
laptop can nest them unchanged. On boot it prints `{"boot":"pillow_uno","plate_pin":2}` once. The
laptop stamps `pillow_id` and real Unix `ts` (`sim/uno_state.py`).

## Flash

Arduino IDE: board "Arduino Uno", open `pillow_uno.ino`, upload. Or:

```bash
arduino-cli compile --fqbn arduino:avr:uno firmware/pillow_uno
arduino-cli upload  --fqbn arduino:avr:uno -p /dev/cu.usbmodem1101 firmware/pillow_uno
```

Unplug the wire from GPIO44 while uploading over USB if the upload fails: the Uno's TX line is
shared between USB and that wire.

## Test it

Bench, Uno straight into the laptop (no Waveshare yet):

```bash
uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --dry             # see the contract messages
uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101                   # posts as test-pillow
uv run sim/uno_bridge.py --port /dev/cu.usbmodem1101 --pillow-id mum   # the real pillow
```

In the pillow, through the voice unit:

```bash
uv run sim/audio_bridge.py --server https://pillow.keanuc.net --pillow-id mum
```

Then press the plate for 5 s and watch `GET /api/pillows/mum/state` flip `head_on`; at night
(or with quiet hours set equal for a daytime demo) Night Watch does the rest.
