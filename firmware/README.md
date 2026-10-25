# Pillow firmware

`pillow/pillow.ino` speaks `coord/CONTRACT.md`: every ~500 ms it reads the sensors, POSTs state to
`SERVER_URL/api/pillows/{PILLOW_ID}/state`, polls `/commands`, and drives the motor and LED.

## Two pillows, two boards

- `pillow/`: **Mum's pillow**, booth ESP32 DevKit + breadboard sensors (pins below).
- `kid_pillow/`: **not used** (decision Sat 24 Oct: no second pillow, the adult child only uses the app).
  Kept for reference: Waveshare ESP32-S3 AMOLED V2, no wiring: screen glows
  "Mum's in bed", flashes "Check on Mum" on alerts, tap or touch = `keys.fine`. FQBN
  `esp32:esp32:esp32s3:CDCOnBoot=cdc`.
- `voice_unit/`: the Waveshare inside Mum's pillow as **speaker + mic only** (ES8311 codec, squeeze
  = "talk"). Bluetooth LE to the laptop (16 kHz mu-law) or ESP-NOW to `espnow_relay/` (below),
  USB serial as a fallback;
  `uv run sim/audio_bridge.py` makes it the speaker and mic for `voice/voice.py`
  (`PILLOW_AUDIO=pillow`). FQBN `esp32:esp32:esp32s3:CDCOnBoot=cdc`, no libraries to install.
  Also reads the Uno's sensor lines (below).
- `pillow_node/`: the Elegoo N16R8 **inside the pillow** next to the Uno: sends the Uno's lines to
  the voice unit over ESP-NOW (the demo layout, below).
- `espnow_relay/` + `libraries/PillowRadio/`: the laptop end of the ESP-NOW link when the voice
  unit is in the pillow (the older layout).
- `i2c_scan/`, `wifi_diag/`: one-off diagnostics (onboard bus = SDA 15 / SCL 14; Wi-Fi reasons).

## Connectivity: USB serial bridge (default)

The venue SSID is almost all 5/6 GHz; the single 2.4 GHz AP is too weak for the ESP32's antenna
(scan from the board does not see it: reason 201, no AP found). The boards never join it. So by default
`secrets.h` defines `SERIAL_BRIDGE`, and each board talks to its laptop over USB:

```bash
python3 sim/serial_bridge.py --port /dev/ttyACM0 --server https://pillow.keanuc.net
```

The board prints `STATE {json}` lines; the bridge POSTs them and writes `CMD {json}` lines back.
Comment out `SERIAL_BRIDGE` to use Wi-Fi instead (e.g. at home).

## Demo layout: pillow node + bedside voice unit

The Waveshare is enclosed (no header to wire), so it sits at the bedside on the laptop's USB, and
the bare N16R8 goes in the pillow with the sensors on its breadboard (the Uno is out: one board,
one supply). One USB cable leaves the pillow to the power bank outside it (no lithium inside bedding).

```
PILLOW                                        BEDSIDE                        LAPTOP
foil plate ──> N16R8 pillow_node ──ESP-NOW──> Waveshare voice_unit ──USB──> audio_bridge.py --server
power bank (outside) ──USB──> N16R8                (mic, speaker, screen)
```

| Part | N16R8 | Note |
|---|---|---|
| head switch plate, sheet 1 | GPIO4 (`PLATE_PIN`, `INPUT_PULLUP`) | pressed reads LOW |
| head switch plate, sheet 2 | GND | |
| passive buzzer | GPIO5 (`BUZZER_PIN`) → 100 Ω → buzzer +, − → GND | plays the server's `buzz`; `-1` = none |
| debug LED | GPIO6 (`LED_PIN`) → 220 Ω → LED → GND | lit while a head is on the plate, follows the notes during a `buzz`; not a server-controlled light; `-1` = none |

S3 pins are 3.3 V only: no 5 V sensor outputs straight in (an HC-SR04 echo needs a 1k/2k divider);
analog only on ADC1 (GPIO1-10); keep off GPIO0/3/45/46 (strapping), 19/20 (USB), 48 (RGB LED).
The node builds the contract line itself ({"head_on":1,"motion":null,...,"talk":0}) every 500 ms
and on change; `sim/uno_state.py`, the bridge and the backend are unchanged from the Uno days.

The voice unit's screen library (GFX Library for Arduino 1.6.4) doesn't compile on esp32 core
3.3.10+ as shipped: run `firmware/patch_gfx.sh` once after installing it (CI does the same).

```bash
L="--libraries firmware/libraries --build-property compiler.cpp.extra_flags=-DPILLOW_LINK=1"
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc $L firmware/voice_unit   # bedside
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/pillow_node
uv run sim/audio_bridge.py --serial <the Waveshare's port> --server https://pillow.keanuc.net
```

The N16R8 devkit has two USB-C sockets. `CDCOnBoot=cdc` puts `Serial` on the native "USB" socket;
on the "COM" socket (the CH343 bridge, shows as "USB Single Serial") build **without** it:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3 --libraries firmware/libraries --build-path firmware/pillow_node/build firmware/pillow_node
arduino-cli upload  --fqbn esp32:esp32:esp32s3 -p /dev/cu.usbmodemXXXX --input-dir firmware/pillow_node/build firmware/pillow_node
```

### Voice unit off the laptop's USB: hotspot, Bluetooth fallback

With both boards in the pillow, the voice unit reaches the laptop by itself. `PILLOW_HOTSPOT=1`
joins the laptop's hidden access point and dials `audio_bridge.py --hotspot` over TCP (port 47801;
the USB lines, both ways). `PILLOW_BLE=1` keeps Bluetooth up as the fallback. ESP-NOW to the node
stays on. All three share one radio, so the access point must be on `RADIO_CHANNEL` (1). The
laptop's Wi-Fi card does AP + client on a single channel only, so pin its venue connection to a
2.4 GHz channel-1 access point first. `HOTSPOT_SSID` / `HOTSPOT_PASS` / `HOTSPOT_HOST` go in the
gitignored `secrets.h`; share them privately, never on the bus.

```bash
F="compiler.cpp.extra_flags=-DPILLOW_LINK=1 -DPILLOW_HOTSPOT=1 -DPILLOW_BLE=1"
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=opi --libraries firmware/libraries \
  --build-property "$F" --build-property build.partitions=huge_app \
  --build-property upload.maximum_size=3145728 firmware/voice_unit   # Wi-Fi + BT: 1.28 MB, over the default 1.25 MB
uv run sim/audio_bridge.py --hotspot 10.42.0.1:47801 --server https://pillow.keanuc.net
```

`PSRAM=opi` is required with Bluetooth: Wi-Fi plus Bluedroid need most of the internal RAM, so the
speaker and hotspot buffers (80 KB) go in the board's 8 MB PSRAM. Without it the BLE controller
fails to start (`BLE_INIT: Malloc failed`) and the board reboots in a loop.

The bridge uses the hotspot while the board is dialled in, and Bluetooth only while it isn't: it
doesn't connect Bluetooth while the hotspot is up, and the board stops advertising. Both matter.
With Bluetooth on, ESP-IDF forces Wi-Fi modem sleep, and a held Bluetooth connection cut the
hotspot's mic audio to ~12k of 16k samples/s with 1.2 s gaps. Standing by, it measured 15.8k with
gaps under 0.4 s. After a hotspot drop, Bluetooth takes a few seconds to scan and connect. A link that
stays silent for 5 s counts as dropped: the board sends at least an `HB` heartbeat every second.
The node's `UNO` lines kept arriving twice a second in every mode.

USB writes never block (`Serial.setTxTimeoutMs(0)`). With the board on a laptop's USB but nobody
reading the port, each line used to stall the sender for 100 ms, which dropped radio lines.

The voice unit's QMI8658 also measures restlessness. `IMU {"ax":..,"gx":..,"motion":0.12}` gives
the share of 50 Hz samples over the last 10 s whose acceleration left its resting tilt by more than
0.03 g, or whose rotation exceeded 15 deg/s. Samples taken while the speaker plays don't count. The
bridge copies it into the state's `motion` while the node's own is null (CONTRACT.md 1).

### Bench: the node on the laptop's USB, no voice unit

The same node, its USB on a laptop, reaches the server without the Waveshare:
`uv run sim/uno_bridge.py --port /dev/cu.usbmodemXXXX --pillow-id test-pillow` posts its lines
as state and writes the server's `buzz` commands back as `BUZZ chime 1` lines (the node's USB
protocol, the same text the voice unit sends it over ESP-NOW). The radio keeps running, so the
Waveshare still pairs and gets the same lines. Use `test-pillow`, never `mum`, from a second laptop:
two bridges on one pillow would each take half of its commands. Announce bench runs on the bus:
the backend's live tests wipe `test-pillow`.

The voice unit's audio stays on USB; the radio carries only the pillow's lines (`UNO {...}`, the
prefix kept from the Uno days) and its talk key (`"talk":1` after `"talk":0`, acked, arrives as
`KEY talk`). The node's LED: red = looking for the voice unit, green = paired, blue blink = a line
sent. On its USB (115200) it prints what it forwards, and a JSON line typed there is forwarded as if
the sensors produced it (`STATS`: link health).

## Wireless voice link: ESP-NOW relay (no access point)

Bluetooth from the pillow to the laptop is the default. The alternative is ESP-NOW: the voice unit
talks straight to a second ESP32-S3 (the Elegoo kit's N16R8, `espnow_relay/`) plugged into the
laptop. Neither board joins or runs a network, so nothing beacons. Packets to the paired board are
encrypted; pairing hellos are not. The relay speaks the voice unit's own USB protocol, so the
bridge is unchanged:

```bash
cp firmware/libraries/PillowRadio/secrets{.example,}.h   # gitignored: channel + keys,
#                                                     the SAME file for both boards
L="--libraries firmware/libraries --build-property compiler.cpp.extra_flags=-DPILLOW_LINK=1"
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc $L firmware/voice_unit   # in the pillow
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc $L firmware/espnow_relay # on the laptop
uv run sim/audio_bridge.py --serial /dev/ttyACM0 --server https://pillow.keanuc.net  # the relay's port
```

Plug the relay into its native "USB" port. If you only have its USB-UART ("COM") port, build it
without `CDCOnBoot=cdc` and add `--baud 921600` to the bridge. The two boards pair by themselves
within a few seconds of both being on ("radio: paired with ..." on each side).

Link defaults: 6 Mbit/s OFDM at 15 dBm, so a body between the boards still gets through. Override
`RADIO_PHY_MODE` / `RADIO_PHY_RATE` / `RADIO_TX_POWER` in `secrets.h`. The relay prints one health
line every 30 s, and again when it gets `STATS` on USB: `radio: paired, rssi -28 dBm, ... queue
drops, ... send fails, ... control msgs lost`. Commands and squeezes are acked and resent; audio is
not. The bridge repeats `MIC ON` every 2 s while something listens; after 6 s without one the
relay turns the mic off.

The Elegoo N16R8 reads GPIO0 low on a USB chip reset, so esptool's usual reset after flashing
leaves it in the ROM bootloader ("waiting for download"). Reset it with the watchdog instead (no
buttons needed): `esptool --port <relay port> --after watchdog-reset read-mac`. Its port number
moves around between resets; `/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_<MAC>-if00`
doesn't. Out of the box it runs Elegoo's TinyUSB demo, which ignores the reset lines: hold BOOT, tap
RST once to flash it the first time.

`PILLOW_LINK=2` is an **experiment**: the relay runs a hidden 2.4 GHz access point and both talk
UDP. A hidden SSID still beacons; **it is a hotspot, so never at the venue**. The relay boots with
the access point off and starts it only on the serial command `AP ON`.

### The Uno (pillow sensors): retired

The sensors now sit on the pillow node itself (demo layout above); `pillow_uno/` is kept for
reference only. This section is the older layout, for a voice unit with a reachable header.

The pillow's sensors are on the starter kit's Arduino Uno R3, which has no radio. The voice unit
reads the Uno's serial output and sends each line on as `UNO <line>` (over the link and its own
USB). The Uno is 5 V and the ESP32-S3 is not 5 V tolerant, so divide its TX down:

| Uno | | Waveshare header |
|---|---|---|
| pin 1 (TX) | 1 kΩ in series, then 2 kΩ to GND at the S3 end | GPIO44 (U0RXD) |
| GND | | GND |

Leave the S3's GPIO43 (TX) unconnected. 9600 baud (`UNO_BAUD` in `voice_unit.ino`): match the Uno
sketch's `Serial.begin()`. Lines with non-text bytes (wrong baud) are dropped. The sketch is
`pillow_uno/` (switch plate on pin 2, one JSON line per 500 ms, see its README); run the laptop bridge
with `--server https://pillow.keanuc.net --pillow-id mum` and each line is posted as pillow state.
Without `--server` it is printed as `board: UNO ...`.

## Build and flash

```bash
cp pillow/secrets.example.h pillow/secrets.h   # gitignored: Wi-Fi, SERVER_URL, PILLOW_ID
arduino-cli core install esp32:esp32           # arduino-esp32 3.x
arduino-cli lib install ArduinoJson OneWire DallasTemperature "DHT sensor library"
arduino-cli compile --fqbn esp32:esp32:esp32 pillow          # booth ESP32 DevKit
arduino-cli upload  --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 pillow
arduino-cli monitor -p /dev/ttyUSB0 -c baudrate=115200      # watch "MPU6050 ok", "wifi up", "cmd ..."
```

For the Waveshare ESP32-S3 AMOLED use `--fqbn esp32:esp32:esp32s3` and **change the pins**: its
onboard I2C bus and GPIOs differ (check its header pinout before wiring).

## Wiring (booth ESP32 DevKit). No soldering: breadboard + jumpers.

| Part | ESP32 pin | Where it lives | Note |
|---|---|---|---|
| MPU6050 | SDA 21, SCL 22, 3V3, GND | pillow pod | motion; I2C address 0x68 |
| KY-001 (DS18B20) | 4, 3V3, GND | just under the pillow surface | warmth = head on (slow) |
| DHT11 | 32, 3V3, GND | inside the pillow under the head | humidity = head on (faster) |
| Hit sensor | 27 | pillow edge | tap = "I'm fine"; if taps don't register the module is active-low, flip the check in `loop()` |
| Ultrasonic HC-SR04 | trig 5, **echo 18 via 1k/2k divider**, 5V, GND | nightstand, aimed at the floor by the bed | **echo is 5 V: the divider protects the ESP32** |
| Photoresistor | 34 + 10k divider | nightstand | ADC1 only (Wi-Fi blocks ADC2) |
| DC motor | 25 → 1k → PN2222 base; emitter GND; collector → motor −; motor + → 5V; 1N4007 across motor, stripe to 5V | pillow pod | breathing pulse, vibrate; tape an off-centre weight on the shaft |
| LED | 26 → 220Ω → LED → GND | bedside | glow, path light; use a transistor for a strip |

Only sensors and the motor go inside the pillow. The ESP32, power and USB stay on the
nightstand; no LiPo inside bedding. Every part we have: `PARTS.md`.

## Tuning (top of `pillow.ino`)

`HEAD_DELTA_C` (1.5 °C) and `HEAD_DELTA_RH` (6 %RH) above a 10-minute rolling minimum mean "head on";
`ROOM_NEAR_CM` (80) means someone is standing by the bed; `MOTION_FULL_SCALE` scales motion to 0..1.
All untested on real hardware: tune them on a real pillow first.
