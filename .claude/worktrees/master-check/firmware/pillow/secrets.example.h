// Copy to secrets.h (gitignored) and fill in.
#pragma once
#define WIFI_SSID "Cal Hacks 13.0"
#define WIFI_PASS "hackers!"
#define SERVER_URL "https://pillow.keanuc.net"  // Cloudflare tunnel to the server; no trailing slash
#define PILLOW_ID "mum"                         // "mum" or "kid"
// Venue 2.4 GHz Wi-Fi is too weak for the ESP32: talk to the laptop over USB instead
// (run sim/serial_bridge.py). Comment out to use Wi-Fi.
#define SERIAL_BRIDGE 1
