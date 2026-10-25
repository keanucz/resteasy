# DHT11 on the existing pillow node

Standalone mode is now the default (`PILLOW_USB_DEBUG=0`). It disables application
USB serial input/output and suppresses radio-library serial logs. ROM startup
output may still exist. ESP-NOW, DHT11 readings, and radio buzz commands remain enabled. USB bench commands and
the local USB-to-server bridge require rebuilding with `PILLOW_USB_DEBUG=1`.
For a power-bank test, disconnect from the Mac and power the same USB socket
from the bank. No serial monitor is required; confirm telemetry at the Waveshare. Keep the power bank outside the pillow.

Connections: module VCC to 3V3, module GND to the common ground, DATA/S to GPIO7.
Identify the module pins by their function, not jumper color. Plate GPIO4, buzzer GPIO5
and the ESP-NOW protocol remain unchanged.

Install `DHT sensor library@1.4.6` (Adafruit) with its Unified Sensor dependency.
Compile with the same native USB configuration as the working pillow node:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries --build-path build-dht11 firmware/pillow_node
```

A separate worker samples every two seconds. The main loop snapshots both values
under a lock and includes `temp_c` (Celsius) and `humidity` (percent RH) in its
existing `UNO` JSON. Failed reads become `null`; they are not substituted with zero
or indefinitely retained. The existing serial and audio bridges already carry
these fields. No Waveshare upload is required to forward them.

Stop the sole serial bridge before any upload; do not also open an IDE serial
monitor. Preserve the working flash before replacing the application, and verify
live sensor readings and radio pairing afterward. Do not upload the old standalone
plate sketch.
