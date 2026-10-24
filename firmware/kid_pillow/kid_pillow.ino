// Kid pillow: the adult child's end, on the Waveshare ESP32-S3-Touch-AMOLED-1.8 (V2, CO5300).
// No external wiring. Speaks coord/CONTRACT.md as pillow_id "kid":
//   in:  glow_presence (Mum is in bed), set_light, pulse (breathing glow), vibrate (alert), stop_all
//   out: tap the pillow (IMU) or touch the screen = keys.fine ("I'm here / I've got it")
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/kid_pillow

#include <WiFi.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <Arduino_GFX_Library.h>
#include "secrets.h"  // WIFI_SSID, WIFI_PASS, SERVER_URL, PILLOW_ID ("kid")

// Board pins (from Waveshare's arduino-v2 pin_config.h; I2C confirmed by scan: SDA 15 / SCL 14)
#define IIC_SDA 15
#define IIC_SCL 14
#define TP_INT 21  // touch controller interrupt, low while touched
#define QMI8658_ADDR 0x6B

Arduino_DataBus *bus = new Arduino_ESP32QSPI(12 /*CS*/, 11 /*SCK*/, 4, 5, 6, 7 /*SDIO0-3*/);
Arduino_CO5300 *gfx = new Arduino_CO5300(bus, GFX_NOT_DEFINED, 0, 368, 448, 16, 0, 0, 0);

const uint32_t LOOP_MS = 500;
const float TAP_G = 0.45;  // accel jump (g) between samples that counts as a tap/squeeze
const uint16_t WARM = 0xFC60, ALERT = 0xF9A0, BLACK = 0x0000, DIM = 0x8410;

NetworkClientSecure tls;
NetworkClient plain;
long lastCommandId = 0;
uint32_t fineUntil = 0;
bool imuOk = false;
float lastAx = 0, lastAy = 0, lastAz = 0, motionAvg = 0;

// What the screen should show; render() draws it only when it changes or animates.
bool presence = false;
uint8_t lightPct = 0;
uint32_t alertUntil = 0;
struct Pulse { bool on; float startBpm, endBpm; uint32_t startMs, durMs; } pulse = {false};
int lastScene = -1;
uint8_t lastBrightness = 0;

// ---------- IMU (QMI8658, raw registers) ----------
void qmiWrite(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(QMI8658_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

void imuInit() {
  Wire.beginTransmission(QMI8658_ADDR);
  Wire.write(0x00);  // WHO_AM_I
  bool present = Wire.endTransmission(false) == 0 && Wire.requestFrom(QMI8658_ADDR, 1) == 1;
  uint8_t who = present ? Wire.read() : 0;
  qmiWrite(0x02, 0x40);  // CTRL1: register address auto-increment
  qmiWrite(0x03, 0x15);  // CTRL2: accel ±4 g, ~250 Hz
  qmiWrite(0x08, 0x01);  // CTRL7: accelerometer on
  imuOk = who == 0x05;
  Serial.printf("QMI8658 who_am_i=0x%02X %s\n", who, imuOk ? "ok" : "UNEXPECTED");
}

bool imuRead(float &ax, float &ay, float &az) {
  Wire.beginTransmission(QMI8658_ADDR);
  Wire.write(0x35);  // AX_L
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(QMI8658_ADDR, 6) != 6) return false;
  int16_t raw[3];
  for (int i = 0; i < 3; i++) raw[i] = Wire.read() | (Wire.read() << 8);  // little-endian
  ax = raw[0] / 8192.0; ay = raw[1] / 8192.0; az = raw[2] / 8192.0;
  return true;
}

// Returns motion 0..1 and latches a tap when the accel jumps.
float sampleImu() {
  float ax, ay, az;
  if (!imuOk || !imuRead(ax, ay, az)) return -1;
  float change = fabs(ax - lastAx) + fabs(ay - lastAy) + fabs(az - lastAz);
  bool first = lastAx == 0 && lastAy == 0 && lastAz == 0;
  lastAx = ax; lastAy = ay; lastAz = az;
  if (!first && change > TAP_G) fineUntil = millis() + 1500;
  motionAvg += (change - motionAvg) * 0.05;
  return constrain(motionAvg / 0.6, 0.0, 1.0);
}

// ---------- screen ----------
void scene(int id, uint16_t colour, const char *line1, const char *line2) {
  if (id == lastScene) return;
  lastScene = id;
  gfx->fillScreen(colour);
  gfx->setTextColor(colour == BLACK ? DIM : BLACK);
  gfx->setTextSize(4);
  gfx->setCursor(24, 180);
  gfx->println(line1);
  gfx->setTextSize(3);
  gfx->setCursor(24, 240);
  gfx->println(line2);
}

void brightness(uint8_t b) {
  if (b == lastBrightness) return;
  lastBrightness = b;
  gfx->setBrightness(b);
}

void render() {
  uint32_t now = millis();
  if (now < alertUntil) {  // alert: urgent amber flash, ~1 Hz
    scene(3, ALERT, "Check on Mum", "tap to reply");
    brightness((now / 500) % 2 ? 255 : 60);
  } else if (pulse.on && now - pulse.startMs < pulse.durMs) {
    uint32_t t = now - pulse.startMs;
    float bpm = pulse.startBpm + (pulse.endBpm - pulse.startBpm) * t / (float)pulse.durMs;
    float level = 0.5 - 0.5 * cos(fmod(t / 60000.0 * bpm, 1.0) * 2 * PI);
    scene(2, WARM, "Breathe with", "Mum");
    brightness(20 + level * 200);
  } else if (presence || lightPct > 0) {
    pulse.on = false;
    scene(1, WARM, "Mum's in bed", "goodnight");
    brightness(presence ? max<uint8_t>(60, lightPct * 2.55) : lightPct * 2.55);
  } else {
    scene(0, BLACK, "", "");
    brightness(0);
  }
}

// ---------- commands ----------
void runCommand(JsonObject c) {
  const char *cmd = c["cmd"] | "";
  JsonObject a = c["args"];
  Serial.printf("cmd %ld %s\n", (long)(c["id"] | 0), cmd);
  if (!strcmp(cmd, "glow_presence")) {
    presence = a["on"] | false;
  } else if (!strcmp(cmd, "set_light")) {
    lightPct = strcmp(a["color"] | "warm", "off") ? constrain(a["brightness_pct"] | 0, 0, 100) : 0;
  } else if (!strcmp(cmd, "pulse")) {
    pulse = {true, a["start_bpm"] | 12.0f, a["end_bpm"] | 6.0f, millis(),
             (uint32_t)constrain(a["duration_min"] | 5, 1, 30) * 60000UL};
  } else if (!strcmp(cmd, "vibrate")) {  // no motor on this board: flash the screen instead
    alertUntil = millis() + 4000UL * constrain(a["repeat"] | 1, 1, 5);
  } else if (!strcmp(cmd, "stop_all")) {
    presence = false; lightPct = 0; alertUntil = 0; pulse.on = false;
  }
}

// ---------- network ----------
bool beginRequest(HTTPClient &http, const String &url) {
  http.setReuse(true);
  http.setTimeout(3000);
  bool secure = strncmp(SERVER_URL, "https://", 8) == 0;
  return secure ? http.begin(tls, url) : http.begin(plain, url);
}

String base() { return String(SERVER_URL) + "/api/pillows/" + PILLOW_ID; }

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  Serial.printf("wifi %s %s\n", WiFi.status() == WL_CONNECTED ? "up" : "down",
                WiFi.localIP().toString().c_str());
}

void postState(float motion) {
  JsonDocument doc;
  doc["pillow_id"] = PILLOW_ID;
  doc["ts"] = millis() / 1000.0;
  doc["head_on"] = false;  // no head sensor on this board
  if (motion < 0) doc["motion"] = nullptr; else doc["motion"] = motion;
  doc["room_motion"] = false;
  doc["light"] = nullptr;
  doc["temp_c"] = nullptr;
  doc["humidity"] = nullptr;
  JsonObject keys = doc["keys"].to<JsonObject>();
  keys["talk"] = false; keys["family"] = false;
  keys["fine"] = millis() < fineUntil;
  doc["knob"] = nullptr;
  String body;
  serializeJson(doc, body);
#ifdef SERIAL_BRIDGE
  Serial.print("STATE ");
  Serial.println(body);
  return;
#endif
  HTTPClient http;
  beginRequest(http, base() + "/state");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  if (code < 200 || code >= 300) Serial.printf("state POST -> %d\n", code);
  http.end();
}

void pollCommands() {
  HTTPClient http;
  beginRequest(http, base() + "/commands?after=" + String(lastCommandId));
  int code = http.GET();
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, http.getString())) {
      for (JsonObject c : doc.as<JsonArray>()) {
        runCommand(c);
        lastCommandId = max(lastCommandId, (long)(c["id"] | 0));
      }
    }
  } else {
    Serial.printf("commands GET -> %d\n", code);
  }
  http.end();
}

// Serial bridge mode: commands arrive as "CMD {json}" lines from sim/serial_bridge.py.
void readSerialCommands() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch != '\n') { if (line.length() < 1024) line += ch; continue; }
    if (line.startsWith("CMD ")) {
      JsonDocument doc;
      if (!deserializeJson(doc, line.substring(4))) runCommand(doc.as<JsonObject>());
    }
    line = "";
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(TP_INT, INPUT_PULLUP);
  Wire.begin(IIC_SDA, IIC_SCL);
  imuInit();
  if (!gfx->begin()) Serial.println("display begin FAILED");
  gfx->fillScreen(BLACK);
  scene(9, WARM, "kid pillow", "connecting...");
  brightness(80);
  tls.setInsecure();
#ifndef SERIAL_BRIDGE
  ensureWifi();
#endif
}

void loop() {
  uint32_t started = millis();
  float motion = sampleImu();
  if (digitalRead(TP_INT) == LOW) fineUntil = millis() + 1500;  // screen touched
#ifdef SERIAL_BRIDGE
  postState(motion);
  readSerialCommands();
#else
  ensureWifi();
  if (WiFi.status() == WL_CONNECTED) {
    postState(motion);
    pollCommands();
  }
#endif
  render();
  uint32_t spent = millis() - started;
  if (spent < LOOP_MS) delay(LOOP_MS - spent);
}
