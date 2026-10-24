// Copy to secrets.h (gitignored) and fill in. The voice unit and the relay must be built with the
// same file. Keys: 16 random bytes each, e.g. python3 -c "import os; print(', '.join(f'0x{b:02x}' for b in os.urandom(16)))"
#pragma once

// 2.4 GHz channel for both boards (1-11 in the US). Pick the quietest one in the room.
#define RADIO_CHANNEL 1

// ESP-NOW encryption: primary master key and the per-peer local master key.
const uint8_t RADIO_PMK[16] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
const uint8_t RADIO_LMK[16] = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

// PILLOW_LINK 2 (experiment) only: the relay's hidden access point. WPA2 password, 8+ characters.
#define RADIO_AP_SSID "change-me"
#define RADIO_AP_PASS "change-me-too"
