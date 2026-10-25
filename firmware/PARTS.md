# Parts we have

Everything on the table for the build, so nobody designs around a part we don't have. Wiring for
what's in use is in `firmware/README.md`; state fields are in `coord/CONTRACT.md`.

## ELEGOO Super Starter Kit (UNO R3 Project)

| Part | Useful for us? |
|---|---|
| UNO R3 board | Spare microcontroller. No Wi-Fi/BLE, so only over USB serial |
| LCD1602 module | Probably not: 5 V parallel (no I2C backpack in the kit), uses 6+ GPIOs |
| Stepper motor + ULN2003 driver board | No |
| Breadboard power supply module | Yes: 5 V / 3.3 V rails for the breadboard |
| SG90 servo | No |
| 5 V relay | No. Never mains at the bedside |
| IR receiver module + IR remote | Maybe: remote buttons as "I'm fine" / "call family" from bed |
| Joystick module | No |
| DHT11 temperature + humidity | **In use**: humidity rise = head on, `temp_c` / `humidity` |
| Ultrasonic sensor (HC-SR04) | **In use**: someone by the bed → `room_motion` (no PIR) |
| Fan blade + 3-6 V DC motor | `fan` command; the motor can also vibrate |
| L293D motor driver | Alternative to the PN2222 motor driver |
| Active buzzer | Loud local alarm if the server is unreachable |
| Passive buzzer | Tones only (it can't play speech) |
| 74HC595 shift register | No |
| 1-digit and 4-digit 7-segment displays | No |
| 5 push buttons | Keys (talk / fine / family) on the nightstand |
| 10k potentiometer | Knob (volume) |
| Tilt switch | Maybe: pillow moved or flipped |
| Thermistor | Backup warmth = head on |
| Photoresistors | **In use**: dark → `light` |
| LEDs, RGB LEDs, resistors | No |
| PN2222 transistors, diodes | **In use**: motor driver (PN2222 + 1N4007) |
| Breadboard, jumper wires | **In use** |
| 9 V battery + snap | Not in bedding |

What the kit doesn't have: **no microphone, no PIR, no accelerometer/IMU, no sound sensor.**

## Reserved from the Cal Hacks hardware booth

1 ESP32 (Mum's pillow, `firmware/pillow/`), 2 MPU6050, 2 DC motors, 2 hit sensors, 2 microphone
sound sensor modules, 2 temperature sensor modules (KY-001 / DS18B20), 1 small passive buzzer.
The sound sensor modules detect loudness only (KY-037/038 style, electret + comparator): fine for
"a noise in the room", not good enough for speech to text.

## Ours

- Keanu's Waveshare ESP32-S3-Touch-AMOLED-1.8: the only speech-grade mic + speaker we have (ES8311
  codec), plus an IMU, screen, LiPo charger, Wi-Fi and BLE.
- 3-key keypad with a knob.
- Szymon's Raspberry Pi + HTN badge.
