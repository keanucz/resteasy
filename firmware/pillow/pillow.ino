// Pillow firmware: speaks coord/CONTRACT.md.
// Every 500 ms: read sensors, POST /api/pillows/{id}/state, GET commands, run them.
// Board: ESP32 (arduino-esp32 core 3.x). Copy secrets.example.h to secrets.h first.

#include <WiFi.h>
#include <HTTPClient.h>
#include <NetworkClientSecure.h>
#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include "secrets.h"  // WIFI_SSID, WIFI_PASS, SERVER_URL, PILLOW_ID

// ---- Pins (generic ESP32 DevKit defaults; check against your board's pinout) ----
#ifndef PIN_SDA
#define PIN_SDA 21          // MPU6050 SDA
#define PIN_SCL 22          // MPU6050 SCL
#endif
#define PIN_ONEWIRE 4       // KY-001 / DS18B20 data (needs its 4.7k pull-up; the module has it)
#define PIN_DHT 32          // DHT11 data, inside the pillow under the head (humidity = head on)
#define PIN_HIT 27          // hit sensor digital out (tap = "I'm fine")
#define PIN_TRIG 5          // ultrasonic trigger
#define PIN_ECHO 18         // ultrasonic echo: 5 V signal, use a 1k/2k divider to 3.3 V
#define PIN_LDR 34          // photoresistor divider, ADC1 only (Wi-Fi blocks ADC2)
#define PIN_MOTOR 25        // to PN2222 base through 1k; motor on 5 V with 1N4007 across it
#define PIN_LED 26          // glow / path light (through a resistor, or a transistor for a strip)

// ---- Tuning (defaults; the server owns event thresholds, these are only sensor cleanup) ----
const uint32_t LOOP_MS = 500;
const float HEAD_DELTA_C = 1.5;      // pillow probe this much above its 10-min minimum = head on
const float HEAD_DELTA_RH = 6.0;     // DHT11 humidity this much above its 10-min minimum = head on
const float ROOM_NEAR_CM = 80;       // ultrasonic closer than this = someone standing by the bed
const float MOTION_FULL_SCALE = 0.6; // accel change (g) that maps to motion = 1.0

OneWire oneWire(PIN_ONEWIRE);
DHT dht(PIN_DHT, DHT11);
DallasTemperature probe(&oneWire);

bool imuOk = false;
float lastAx = 0, lastAy = 0, lastAz = 0;
float motionAvg = 0;            // ~10 s exponential average of accel change
float probeMinC = 100;          // rolling minimum of the pillow probe
float humidMinRh = 100;         // rolling minimum of the in-pillow humidity
uint32_t baselineResetAt = 0;
bool headOn = false;
bool warmHead = false, humidHead = false;
uint32_t fineUntil = 0;         // hit sensor latch so a tap survives one state message
long lastCommandId = 0;

// One TLS connection, reused for every request (a fresh handshake twice a second is too slow).
// setInsecure() skips certificate checks: acceptable for the hackathon, not for production.
NetworkClientSecure tls;
NetworkClient plain;
bool useTls() { return strncmp(SERVER_URL, "https://", 8) == 0; }

bool beginRequest(HTTPClient &http, const String &url) {
  http.setReuse(true);
  http.setTimeout(3000);
  return useTls() ? http.begin(tls, url) : http.begin(plain, url);
}

// Actuator state, updated by commands and advanced every loop
struct Pulse { bool on; float startBpm, endBpm; uint32_t startMs, durMs; } pulse = {false};
uint8_t lightPct = 0, fanPct = 0;
uint32_t vibrateUntil = 0;
bool presenceGlow = false;

// ---------- sensors ----------
void imuInit() {
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.beginTransmission(0x68);
  Wire.write(0x6B);  // PWR_MGMT_1
  Wire.write(0x00);  // wake
  imuOk = Wire.endTransmission() == 0;
  Serial.printf("MPU6050 %s\n", imuOk ? "ok" : "NOT FOUND (check SDA/SCL, address 0x68)");
}

bool imuRead(float &ax, float &ay, float &az) {
  Wire.beginTransmission(0x68);
  Wire.write(0x3B);  // ACCEL_XOUT_H
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(0x68, 6) != 6) return false;
  int16_t raw[3];
  for (int i = 0; i < 3; i++) raw[i] = (Wire.read() << 8) | Wire.read();
  ax = raw[0] / 16384.0; ay = raw[1] / 16384.0; az = raw[2] / 16384.0;  // ±2 g range
  return true;
}

float readMotion() {
  float ax, ay, az;
  if (!imuOk || !imuRead(ax, ay, az)) return -1;
  float change = fabs(ax - lastAx) + fabs(ay - lastAy) + fabs(az - lastAz);
  lastAx = ax; lastAy = ay; lastAz = az;
  motionAvg += (change - motionAvg) * 0.05;  // 0.05 per 500 ms ≈ 10 s time constant
  return constrain(motionAvg / MOTION_FULL_SCALE, 0.0, 1.0);
}

float readProbeC() {
  probe.requestTemperatures();
  float c = probe.getTempCByIndex(0);
  return c == DEVICE_DISCONNECTED_C ? NAN : c;
}

// Head on pillow = warmth (KY-001) OR breath/skin humidity (DHT11) above a rolling baseline.
// Humidity responds faster than the probe's temperature, so either sensor alone can say "on";
// each has hysteresis so it doesn't flicker. Baselines follow the room every 10 min.
void hysteresis(bool &state, float delta, float threshold) {
  if (!state && delta > threshold) state = true;
  else if (state && delta < threshold * 0.5) state = false;
}

void updateHeadOn(float probeC, float humidRh) {
  if (millis() > baselineResetAt) {
    if (!isnan(probeC)) probeMinC = probeC;
    if (!isnan(humidRh)) humidMinRh = humidRh;
    baselineResetAt = millis() + 600000UL;
  }
  if (!isnan(probeC)) {
    probeMinC = min(probeMinC, probeC);
    hysteresis(warmHead, probeC - probeMinC, HEAD_DELTA_C);
  }
  if (!isnan(humidRh)) {
    humidMinRh = min(humidMinRh, humidRh);
    hysteresis(humidHead, humidRh - humidMinRh, HEAD_DELTA_RH);
  }
  headOn = warmHead || humidHead;
}

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW); delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 25000);  // ~4 m max, 25 ms timeout
  return us == 0 ? NAN : us / 58.0;
}

// ---------- actuators ----------
void applyActuators() {
  uint8_t motorDuty = 0, ledDuty = map(lightPct, 0, 100, 0, 255);
  if (pulse.on) {
    uint32_t t = millis() - pulse.startMs;
    if (t >= pulse.durMs) {
      pulse.on = false;
    } else {
      float bpm = pulse.startBpm + (pulse.endBpm - pulse.startBpm) * t / (float)pulse.durMs;
      float phase = fmod(t / 60000.0 * bpm, 1.0);       // 0..1 within one breath
      float level = 0.5 - 0.5 * cos(phase * 2 * PI);     // smooth in and out
      motorDuty = 90 + level * 120;                      // gentle; tune by feel
      ledDuty = max<uint8_t>(ledDuty, level * 180);
    }
  }
  if (millis() < vibrateUntil) motorDuty = 220;
  if (fanPct > 0 && motorDuty == 0) motorDuty = map(fanPct, 0, 100, 0, 255);
  if (presenceGlow) ledDuty = max<uint8_t>(ledDuty, 40);
  ledcWrite(PIN_MOTOR, motorDuty);
  ledcWrite(PIN_LED, ledDuty);
}

void runCommand(JsonObject c) {
  const char *cmd = c["cmd"] | "";
  JsonObject a = c["args"];
  Serial.printf("cmd %ld %s\n", (long)(c["id"] | 0), cmd);
  if (!strcmp(cmd, "set_light")) {
    lightPct = strcmp(a["color"] | "warm", "off") ? constrain(a["brightness_pct"] | 0, 0, 100) : 0;
  } else if (!strcmp(cmd, "pulse")) {
    pulse = {true, a["start_bpm"] | 12.0f, a["end_bpm"] | 6.0f, millis(),
             (uint32_t)constrain(a["duration_min"] | 5, 1, 30) * 60000UL};
  } else if (!strcmp(cmd, "vibrate")) {
    vibrateUntil = millis() + 300UL * constrain(a["repeat"] | 1, 1, 5);
  } else if (!strcmp(cmd, "fan")) {
    fanPct = constrain(a["speed_pct"] | 0, 0, 100);
  } else if (!strcmp(cmd, "glow_presence")) {
    presenceGlow = a["on"] | false;
  } else if (!strcmp(cmd, "stop_all")) {
    pulse.on = false; lightPct = 0; fanPct = 0; vibrateUntil = 0; presenceGlow = false;
  }
}

// ---------- network ----------
String base() { return String(SERVER_URL) + "/api/pillows/" + PILLOW_ID; }

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  Serial.printf("wifi %s %s\n", WiFi.status() == WL_CONNECTED ? "up" : "down",
                WiFi.localIP().toString().c_str());
}

void postState(float motion, float probeC, float humidRh, float distCm, float light) {
  JsonDocument doc;
  doc["pillow_id"] = PILLOW_ID;
  doc["ts"] = millis() / 1000.0;  // device clock; the server stamps arrival time too
  doc["head_on"] = headOn;
  if (motion < 0) doc["motion"] = nullptr; else doc["motion"] = motion;
  doc["room_motion"] = !isnan(distCm) && distCm < ROOM_NEAR_CM;
  doc["light"] = light;
  if (isnan(probeC)) doc["temp_c"] = nullptr; else doc["temp_c"] = probeC;
  if (isnan(humidRh)) doc["humidity"] = nullptr; else doc["humidity"] = humidRh;
  JsonObject keys = doc["keys"].to<JsonObject>();
  keys["talk"] = false; keys["family"] = false;  // the USB keypad goes to the base laptop
  keys["fine"] = millis() < fineUntil;
  doc["knob"] = nullptr;
  String body;
  serializeJson(doc, body);
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

void setup() {
  Serial.begin(115200);
  pinMode(PIN_HIT, INPUT);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  ledcAttach(PIN_MOTOR, 1000, 8);  // core 3.x API: pin, Hz, bits
  ledcAttach(PIN_LED, 5000, 8);
  imuInit();
  probe.begin();
  dht.begin();
  probe.setWaitForConversion(true);
  tls.setInsecure();
  ensureWifi();
}

void loop() {
  uint32_t started = millis();
  if (digitalRead(PIN_HIT) == HIGH) fineUntil = millis() + 1200;  // flip to LOW if your module is active-low
  float motion = readMotion();
  float probeC = readProbeC();
  float humidRh = dht.readHumidity();  // NAN if not wired; the library rate-limits to every 2 s
  updateHeadOn(probeC, humidRh);
  float distCm = readDistanceCm();
  float light = analogRead(PIN_LDR) / 4095.0;
  ensureWifi();
  if (WiFi.status() == WL_CONNECTED) {
    postState(motion, probeC, humidRh, distCm, light);
    pollCommands();
  }
  applyActuators();
  uint32_t spent = millis() - started;
  if (spent < LOOP_MS) delay(LOOP_MS - spent);
}
