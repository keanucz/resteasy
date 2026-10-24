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
  = "talk"). Bluetooth LE to the laptop (16 kHz mu-law), USB serial as a fallback;
  `uv run sim/audio_bridge.py` makes it the speaker and mic for `voice/voice.py`
  (`PILLOW_AUDIO=pillow`). FQBN `esp32:esp32:esp32s3:CDCOnBoot=cdc`, no libraries to install.
- `i2c_scan/`, `wifi_diag/`: one-off diagnostics (onboard bus = SDA 15 / SCL 14; Wi-Fi reasons).

## Connectivity: USB serial bridge (default)

The venue SSID is almost all 5/6 GHz; the single 2.4 GHz AP is too weak for the ESP32's antenna
(scan from the board does not see it: reason 201, no AP found). Hotspots are banned. So by default
`secrets.h` defines `SERIAL_BRIDGE`, and each board talks to its laptop over USB:

```bash
python3 sim/serial_bridge.py --port /dev/ttyACM0 --server https://pillow.keanuc.net
```

The board prints `STATE {json}` lines; the bridge POSTs them and writes `CMD {json}` lines back.
Comment out `SERIAL_BRIDGE` to use Wi-Fi instead (e.g. at home).

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
