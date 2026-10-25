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
// Buzzer: the kit's passive buzzer, BUZZER_PIN -> 100 ohm -> buzzer +, buzzer - -> GND. It plays
//   the server's `buzz` command ("BUZZ chime 1", from the voice unit over ESP-NOW: firmware/libraries/
//   PillowBuzz). Our hellos tell the voice unit a buzzer is here, so it doesn't play the same sound
//   on its speaker too. No buzzer wired: set BUZZER_PIN to -1 and the voice unit plays it instead.
//
// Debug LED (optional): LED_PIN -> 220 ohm -> LED -> GND. Lit while the plate reads a head; while a
//   buzz plays it follows the notes, so a bench with no buzzer still shows the command arrived.
//   Not a light the server controls (set_light is the voice unit's screen). -1 = none wired.
//
// Power: the node on its own USB cable from the power bank outside the pillow (no lithium in bedding).
//
// RGB LED: red = looking for the voice unit, green = paired, blue blink = a line sent.
// USB (115200, debugging only): every forwarded line, link events, STATS every 30 s. A JSON line
// typed on USB is forwarded as if the sensors produced it: a bench test. "STATS" prints link health,
// "BUZZ chime 1" plays the buzzer.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/pillow_node
// The voice unit must be built with PILLOW_LINK=1, and both with the same secrets.h.
// On the devkit's "COM" socket (the CH343 UART bridge, "USB Single Serial") drop CDCOnBoot=cdc so
// Serial comes out there; with it, Serial is on the native "USB" socket only.

#include <PillowBuzz.h>
#include <PillowRadio.h>
#include "driver/gpio.h"

#define PLATE_PIN 4   // <- one foil sheet; the other sheet -> GND
#define BUZZER_PIN 5  // -> 100 ohm -> passive buzzer; -1 = none wired
#define LED_PIN 6     // -> 220 ohm -> debug LED -> GND; -1 = none wired
const uint8_t HELLO_HAS_BUZZER = 2;  // bit in our hellos' app byte (firmware/libraries/PillowRadio)

const uint32_t REPORT_MS = 500;        // the contract's ~2 reports per second
const uint32_t PLATE_DEBOUNCE_MS = 150; // foil bounce and a head shifting; meaning is the server's
const size_t STATE_LINE_MAX = 200;
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

// ---------- buzzer ----------
bool buzzLit = false;  // a note is sounding: the debug LED follows it

void buzzerOut(uint16_t hz) {
  buzzLit = hz != 0;
#if BUZZER_PIN >= 0
  if (hz) tone(BUZZER_PIN, hz);
  else noTone(BUZZER_PIN);
#endif
}

buzz::Player buzzer(buzzerOut);
// A BUZZ from the radio task, picked up by loop(): the player is only touched from loop()
portMUX_TYPE buzzMux = portMUX_INITIALIZER_UNLOCKED;
bool buzzPending = false;
buzz::Pattern buzzPattern = buzz::CHIME;
int buzzRepeat = 1;

void requestBuzz(const String &cmd) {
  buzz::Pattern pattern;
  int repeat;
  if (!buzz::parse(cmd, pattern, repeat)) return;
  portENTER_CRITICAL(&buzzMux);
  buzzPattern = pattern;
  buzzRepeat = repeat;
  buzzPending = true;
  portEXIT_CRITICAL(&buzzMux);
}

void startPendingBuzz() {
  portENTER_CRITICAL(&buzzMux);
  bool pending = buzzPending;
  buzz::Pattern pattern = buzzPattern;
  int repeat = buzzRepeat;
  buzzPending = false;
  portEXIT_CRITICAL(&buzzMux);
  if (!pending) return;
  Serial.printf("buzz: %s x%d\n", pattern.notes == buzz::CHIME.notes ? "chime" : "alert", repeat);
  buzzer.start(pattern, repeat);
}

// From the voice unit: hellos, and C packets (acked, once each): "BUZZ chime 1". On the radio task.
void onRadio(char type, const uint8_t *data, size_t len) {
  if (type == radio::PKT_CMD) requestBuzz(String((const char *)data, len));
}

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
  if (line.startsWith("BUZZ ")) {  // typed on USB
    requestBuzz(line);
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

void showLed() {
#if LED_PIN >= 0
  digitalWrite(LED_PIN, (buzzer.playing() ? buzzLit : headOn) ? HIGH : LOW);
#endif
}

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
  s.reserve(STATE_LINE_MAX);
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
      else if (line.length() < STATE_LINE_MAX) line += ch;
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
#if LED_PIN >= 0
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
#endif
#if BUZZER_PIN >= 0
  radio::helloApp = HELLO_HAS_BUZZER;
#endif
  bool ok = radio::begin(LINK_ESPNOW, false, onRadio);
  Serial.printf("pillow_node: esp-now %s on channel %d, mac %s, plate gpio %d, buzzer gpio %d, led gpio %d\n",
                ok ? "started" : "FAILED", RADIO_CHANNEL, WiFi.macAddress().c_str(), PLATE_PIN, BUZZER_PIN, LED_PIN);
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
  startPendingBuzz();
  buzzer.update();
  showLed();
  showLink();
  if (now - lastStats >= STATS_MS) {
    lastStats = now;
    printStats();
  }
  delay(2);
}
