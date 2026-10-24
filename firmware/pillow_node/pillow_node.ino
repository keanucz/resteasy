// Pillow node: an ESP32-S3 (the Elegoo kit's ESP32-S3-N16R8) inside the pillow, next to the Uno.
// The Uno has the sensors and no radio; this board reads its serial lines and sends each one over
// ESP-NOW (firmware/libraries/PillowRadio) to the voice unit at the bedside, which prints them on
// its USB as "UNO <line>" for sim/audio_bridge.py. A press of the Uno's talk key ("talk":1 after
// "talk":0) also goes as an acked "talk" event, the same as a squeeze of the voice unit.
//
// Wiring (the Uno is 5 V, the S3 is not 5 V tolerant):
//   Uno pin 1 (TX) -> 1k -> GPIO18, and 2k from GPIO18 to GND
//   Uno GND -> GND,  Uno 5V -> 5V  (one supply for both, outside the pillow: 9 V battery or power bank)
// Unplug the 5V wire before plugging this board's USB into a laptop: never two 5 V sources.
//
// RGB LED: red = looking for the voice unit, green = paired, blue blink = a line sent.
// USB (115200, debugging only): every forwarded line, link events, STATS every 30 s. A line typed
// on USB is forwarded as if the Uno sent it: a bench test without the Uno. "STATS" prints link health.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/pillow_node
// The voice unit must be built with PILLOW_LINK=1, and both with the same secrets.h.

#include <PillowRadio.h>
#include "driver/gpio.h"

#define UNO_RX 18  // <- Uno pin 1 (TX) via the 1k/2k divider
#define UNO_TX 17  // unused: leave unwired

const uint32_t UNO_BAUD = 9600;  // match the Uno sketch's Serial.begin()
const size_t UNO_LINE_MAX = 200;
const uint32_t STATS_MS = 30000, BLINK_MS = 40;
const uint8_t LED_LEVEL = 24;  // of 255: visible through the pillow, not a night light

uint32_t blinkUntil = 0;

void showLink() {
#ifdef RGB_BUILTIN
  if (millis() < blinkUntil) rgbLedWrite(RGB_BUILTIN, 0, 0, LED_LEVEL);
  else if (radio::paired) rgbLedWrite(RGB_BUILTIN, 0, LED_LEVEL, 0);
  else rgbLedWrite(RGB_BUILTIN, LED_LEVEL, 0, 0);
#endif
}

// Nothing comes back from the voice unit but hellos: it has no commands for the pillow.
void onRadio(char, const uint8_t *, size_t) {}

// The talk key's value in a line like {"head_on":1,...,"talk":0,...}: 1, 0, or -1 if absent
int talkKey(const String &line) {
  int i = line.indexOf("\"talk\":");
  if (i < 0) return -1;
  i += 7;
  while (i < (int)line.length() && line[i] == ' ') i++;
  if (i >= (int)line.length()) return -1;
  return line[i] == '1' || line[i] == 't' ? 1 : 0;  // 1 or true
}

void printStats() {
  char line[200];
  radio::formatStats(line, sizeof(line));
  Serial.println(line);
}

void forward(const String &line) {
  if (line == "STATS") {  // typed on USB
    printStats();
    return;
  }
  String out = "UNO " + line;
  Serial.println(out);
  if (radio::sendText(radio::PKT_LINE, out.c_str())) blinkUntil = millis() + BLINK_MS;
  static int lastTalk = 0;
  int talk = talkKey(line);
  if (talk == 1 && lastTalk == 0) {
    Serial.println("KEY talk");
    radio::sendReliableText(radio::PKT_EVENT, "talk");  // acked and resent: never lost
  }
  if (talk >= 0) lastTalk = talk;
}

// Lines from the Uno, or typed on USB (one reader per stream)
void readLines(Stream &in, String &line, bool &garbled) {
  while (in.available()) {
    char ch = in.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (ch == '\t') ch = ' ';
      if (ch < 0x20 || ch > 0x7e) garbled = true;
      else if (line.length() < UNO_LINE_MAX) line += ch;
      continue;
    }
    if (!garbled && line.length()) forward(line);
    line = "";
    garbled = false;
  }
}

void setup() {
  Serial.begin(115200);
  Serial1.setRxBufferSize(1024);  // ~1 s at 9600 baud: a "talk" send can wait ~0.4 s on its ack
  Serial1.begin(UNO_BAUD, SERIAL_8N1, UNO_RX, UNO_TX);
  gpio_pullup_en((gpio_num_t)UNO_RX);  // idle high when no Uno is wired: no garbage lines
  bool ok = radio::begin(LINK_ESPNOW, false, onRadio);
  Serial.printf("pillow_node: esp-now %s on channel %d, mac %s, uno rx gpio %d @ %u\n", ok ? "started" : "FAILED",
                RADIO_CHANNEL, WiFi.macAddress().c_str(), UNO_RX, (unsigned)UNO_BAUD);
}

void loop() {
  static String unoLine, usbLine;
  static bool unoGarbled = false, usbGarbled = false;  // wrong baud or a floating pin: drop the line
  readLines(Serial1, unoLine, unoGarbled);
  readLines(Serial, usbLine, usbGarbled);
  showLink();
  static uint32_t lastStats = 0;
  if (millis() - lastStats >= STATS_MS) {
    lastStats = millis();
    printStats();
  }
  delay(1);
}
