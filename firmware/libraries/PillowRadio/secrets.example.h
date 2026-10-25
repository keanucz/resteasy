// Copy to secrets.h (gitignored) and fill in. The voice unit and the relay must be built with the
// same file. Keys: 16 random bytes each, e.g. python3 -c "import os; print(', '.join(f'0x{b:02x}' for b in os.urandom(16)))"
#pragma once

// 2.4 GHz channel for both boards (1-11 in the US). Pick the quietest one in the room.
#define RADIO_CHANNEL 1

// ESP-NOW encryption: primary master key and the per-peer local master key.
const uint8_t RADIO_PMK[16] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
const uint8_t RADIO_LMK[16] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

// Optional: radio rate and power (defaults in PillowRadio.h: 6 Mbit/s OFDM, 15 dBm). Sturdier
// still, at a third of the airtime left for retries: 802.11b at 2 Mbit/s.
// #define RADIO_PHY_MODE WIFI_PHY_MODE_11B
// #define RADIO_PHY_RATE WIFI_PHY_RATE_2M_L
// #define RADIO_TX_POWER WIFI_POWER_19_5dBm

// PILLOW_LINK 2 (experiment) only: the relay's hidden access point. WPA2 password, 8+ characters.
#define RADIO_AP_SSID "change-me"
#define RADIO_AP_PASS "change-me-too"

// voice_unit PILLOW_HOTSPOT=1 only: the laptop's hidden hotspot (on RADIO_CHANNEL) and its address there.
#define HOTSPOT_SSID "change-me"
#define HOTSPOT_PASS "change-me-too"
#define HOTSPOT_HOST "10.42.0.1"
