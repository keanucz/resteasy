// Pillow node: an ESP32-S3 (the Elegoo kit's ESP32-S3-N16R8) inside the pillow, with the sensors on
// its breadboard. No Uno any more. It reads the sensors, builds one CONTRACT-shaped JSON line
// (coord/CONTRACT.md 1) every 500 ms and on every change, and sends it over ESP-NOW
// (firmware/libraries/PillowRadio) to the voice unit at the bedside, which prints it on its USB as
// "UNO <line>" for sim/audio_bridge.py --server (the name stayed from the Uno days; the laptop side,
// sim/uno_state.py, is unchanged). The node never decides what a reading means: lay_down (5 s),
// bed_exit (30 s) and the sleep rules live on the server.
//
// Sensors (3.3 V only: the S3 is not 5 V tolerant; ADC1 = GPIO1-10 for analog; avoid GPIO0/3/45/46
// (strapping), 19/20 (USB), 48 (RGB LED), 18/17 (kept free for a UART)):
//   head switch plate: two foil-faced cardboard sheets, a head pressing them together closes the
//     circuit. One sheet -> PLATE_PIN (INPUT_PULLUP, pressed reads LOW), the other -> GND.
//   (room light, temp/humidity, motion: not wired yet, reported as null)
//
// Power: the node on its own USB cable from the power bank outside the pillow (no lithium in bedding).
//
// RGB LED: red = looking for the voice unit, green = paired, blue blink = a line sent.
// USB (115200, debugging only): every forwarded line, link events, STATS every 30 s. A JSON line
// typed on USB is forwarded as if the sensors produced it: a bench test. "STATS" prints link health.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/pillow_node
// The voice unit must be built with PILLOW_LINK=1, and both with the same secrets.h.

#include <PillowRadio.h>
#include "driver/gpio.h"

#define PLATE_PIN 4  // <- one foil sheet; the other sheet -> GND

const uint32_t REPORT_MS = 500;        // the contract's ~2 reports per second
const uint32_t PLATE_DEBOUNCE_MS = 150; // foil bounce and a head shifting; meaning is the server's
const size_t LINE_MAX = 200;
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

// ---------- sensors ----------

bool headOn = false;  // debounced plate contact
bool plateRaw = false;
uint32_t plateSince = 0;

// Returns true when the debounced reading changed.
bool readPlate(uint32_t now) {
  bool pressed = digitalRead(PLATE_PIN) == LOW;
  if (pressed != plateRaw) {
    plateRaw = pressed;
    plateSince = now;
  }
  if (plateRaw != headOn && now - plateSince >= PLATE_DEBOUNCE_MS) {
    headOn = plateRaw;
    return true;
  }
  return false;
}

// The same line the Uno sketch printed, so nothing downstream changes. Unwired sensors are null.
String stateLine() {
  String s;
  s.reserve(LINE_MAX);
  s += "{\"head_on\":";
  s += headOn ? "1" : "0";
  s += ",\"motion\":null,\"room_motion\":null,\"light\":null,\"temp_c\":null,\"humidity\":null";
  s += ",\"fine\":0,\"talk\":0,\"family\":0}";
  return s;
}

// A JSON line typed on USB: a bench test without the sensors
void readUsb(String &line, bool &garbled) {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (ch == '\t') ch = ' ';
      if (ch < 0x20 || ch > 0x7e) garbled = true;
      else if (line.length() < LINE_MAX) line += ch;
      continue;
    }
    if (!garbled && line.length()) forward(line);
    line = "";
    garbled = false;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PLATE_PIN, INPUT_PULLUP);
  bool ok = radio::begin(LINK_ESPNOW, false, onRadio);
  Serial.printf("pillow_node: esp-now %s on channel %d, mac %s, plate gpio %d\n", ok ? "started" : "FAILED",
                RADIO_CHANNEL, WiFi.macAddress().c_str(), PLATE_PIN);
}

void loop() {
  static String usbLine;
  static bool usbGarbled = false;
  static uint32_t lastReport = 0, lastStats = 0;
  uint32_t now = millis();

  bool changed = readPlate(now);
  if (changed || now - lastReport >= REPORT_MS) {
    lastReport = now;
    forward(stateLine());  // on change at once: don't make the server wait for the next tick
  }
  readUsb(usbLine, usbGarbled);
  showLink();
  if (now - lastStats >= STATS_MS) {
    lastStats = now;
    printStats();
  }
  delay(2);
}
