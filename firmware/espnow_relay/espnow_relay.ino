// Relay: an ESP32-S3 (the Elegoo kit's ESP32-S3-N16R8) on the laptop's USB, the far end of the
// voice unit's radio link (firmware/libraries/PillowRadio). On USB it speaks exactly the voice
// unit's own serial protocol, so sim/audio_bridge.py works unchanged:
//
//   uv run sim/audio_bridge.py --serial /dev/ttyACM0
//
//   relay -> laptop:  MIC <base64 of 16 kHz mono s16le>,  KEY talk,  UNO <line>,  log lines
//   laptop -> relay:  SPK <base64 s16le>,  MIC ON|OFF,  VOL n,  GAIN n  (passed on to the voice unit)
//                     AP ON | AP OFF  (PILLOW_LINK 2 only: the hidden access point starts off)
//
// Build (LINK_ESPNOW by default; -DPILLOW_LINK=2 for the access point experiment):
//   arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/espnow_relay
// CDCOnBoot=cdc: plug in the board's native USB port. On its USB-UART ("COM") port instead, build
// without it and run the bridge with --baud 921600.

#include <PillowRadio.h>
#include "mbedtls/base64.h"

#ifndef PILLOW_LINK
#define PILLOW_LINK LINK_ESPNOW
#endif

SemaphoreHandle_t usbLock;  // whole lines only: the radio task and loop() both write to USB
volatile bool micOn = false;

void usbLine(const char *prefix, const char *text, size_t len) {
  xSemaphoreTake(usbLock, portMAX_DELAY);
  Serial.print(prefix);
  Serial.write((const uint8_t *)text, len);
  Serial.println();
  xSemaphoreGive(usbLock);
}

// Radio -> USB (on the radio task)
void onRadio(char type, const uint8_t *data, size_t len) {
  if (type == radio::PKT_MIC) {
    static int16_t pcm[radio::MAX_PACKET];
    static unsigned char b64[((radio::MAX_PACKET * 2 + 2) / 3) * 4 + 1];
    for (size_t i = 0; i < len; i++) pcm[i] = radio::ulawDecode(data[i]);
    size_t n = 0;
    if (mbedtls_base64_encode(b64, sizeof(b64), &n, (const unsigned char *)pcm, len * 2) == 0)
      usbLine("MIC ", (const char *)b64, n);
  } else if (type == radio::PKT_EVENT && len == 4 && memcmp(data, "talk", 4) == 0) {
    usbLine("KEY talk", "", 0);
  } else if (type == radio::PKT_LINE) {
    usbLine("", (const char *)data, len);
  }
}

// USB -> radio
void sendSpeaker(const String &line) {
  static unsigned char pcm[4096];
  static uint8_t ulaw[sizeof(pcm) / 2];
  size_t len = 0;
  if (mbedtls_base64_decode(pcm, sizeof(pcm), &len, (const unsigned char *)line.c_str() + 4, line.length() - 4))
    return;
  size_t n = len / 2;
  for (size_t i = 0; i < n; i++) ulaw[i] = radio::ulawEncode(((int16_t *)pcm)[i]);
  for (size_t i = 0; i < n; i += radio::AUDIO_CHUNK)
    radio::send(radio::PKT_SPK, ulaw + i, min(radio::AUDIO_CHUNK, n - i));
}

void handleUsbLine(const String &line) {
  if (line.startsWith("SPK ")) {
    sendSpeaker(line);
    return;
  }
#if PILLOW_LINK == LINK_WIFI
  if (line == "AP ON" || line == "AP OFF") {
    bool on = line == "AP ON";
    if (on) {
      bool ok = radio::startAccessPoint();
      Serial.printf("relay: hidden access point %s on channel %d\n", ok ? "up" : "FAILED", RADIO_CHANNEL);
    } else {
      radio::stopAccessPoint();
      Serial.println("relay: access point off");
    }
    return;
  }
#endif
  if (line == "MIC ON" || line == "MIC OFF") {
    micOn = line == "MIC ON";
    radio::helloApp = micOn;  // a voice unit that reboots picks the mic state up from our hellos
  }
  radio::sendText(radio::PKT_CMD, line.c_str());
}

void readUsb() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') { if (line.length() < 6000) line += ch; continue; }
    handleUsbLine(line);
    line = "";
  }
}

void setup() {
  Serial.setRxBufferSize(16384);  // SPK lines arrive in bursts
  Serial.begin(921600);
  usbLock = xSemaphoreCreateMutex();
  bool ok = radio::begin(PILLOW_LINK, true, onRadio);
#if PILLOW_LINK == LINK_WIFI
  Serial.printf("relay: udp %s; hidden access point is OFF. Send \"AP ON\" to start it (it is a hotspot: never at the venue)\n",
                ok ? "ready" : "FAILED");
#else
  Serial.printf("relay: esp-now %s on channel %d, mac %s, waiting for the voice unit\n", ok ? "ready" : "FAILED",
                RADIO_CHANNEL, WiFi.macAddress().c_str());
#endif
}

void loop() {
  readUsb();
  static uint32_t lastReport = 0, reportedFails = 0;
  if (millis() - lastReport >= 30000) {
    lastReport = millis();
    if (radio::sendFails != reportedFails) {
      Serial.printf("relay: %u radio sends failed so far\n", (unsigned)radio::sendFails);
      reportedFails = radio::sendFails;
    }
  }
  delay(1);
}
