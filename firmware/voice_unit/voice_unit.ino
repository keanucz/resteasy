// Voice unit: the Waveshare ESP32-S3-Touch-AMOLED-1.8 in Mum's pillow, used only as a speaker and
// microphone. It posts no state: the booth ESP32 is "mum". sim/audio_bridge.py on the laptop turns
// it into a local speaker + mic for voice/voice.py, over USB serial (always on) plus one wireless
// link, chosen at build time with PILLOW_LINK:
//
//   LINK_BLE (0, default)  Bluetooth LE straight to the laptop, below
//   LINK_ESPNOW (1)        ESP-NOW to the relay board on the laptop's USB (firmware/espnow_relay)
//   LINK_WIFI (2)          the relay's hidden 2.4 GHz access point + UDP. Experiment: it is a
//                          hotspot, never at the venue
//
// The radio links carry the same audio and commands: firmware/libraries/PillowRadio.
//
// Bluetooth LE: peripheral "pillow-voice", one GATT service. Audio is 16 kHz G.711 mu-law
// (8 bits a sample, 128 kbit/s), small enough for BLE with room to spare.
//   MIC   notify  mic audio, only while the mic is on
//   SPK   write   audio to play (write without response; the bridge paces it to real time)
//   CTRL  write   text: "MIC ON", "MIC OFF", "VOL <0-100>", "GAIN <0-7>" (mic gain, 6 dB steps)
//   EVENT notify  "talk": a squeeze/tap of the pillow (IMU jump), "I want to say something";
//                 or "UNO <line>", a line from the Uno
//
// USB serial (fallback, when the board is plugged into the laptop): the same as text lines.
//   board -> laptop:  MIC <base64 of 100 ms 16 kHz mono s16le>,  KEY talk,  UNO <line>,  boot log
//   laptop -> board:  SPK <base64 s16le>,  MIC ON|OFF,  VOL n,  GAIN n
//
// Uno passthrough: the Arduino Uno R3 with the pillow's sensors has no radio, so its serial output
// (pin 1, TX) comes in on UNO_RX, through a 1k/2k divider (the Uno is 5 V, the S3 3.3 V). Each line
// goes on over the wireless link and USB as "UNO <line>", unchanged.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc firmware/voice_unit
//   radio: add --libraries firmware/libraries --build-property compiler.cpp.extra_flags=-DPILLOW_LINK=1
// Codec driver es8311.* is Espressif's (Apache-2.0), as shipped in Waveshare's 15_ES8311 example.

#include <Wire.h>
#include <ESP_I2S.h>
#include "driver/gpio.h"
#include "mbedtls/base64.h"
#include "freertos/stream_buffer.h"
#include "es8311.h"

#ifndef PILLOW_LINK
#define PILLOW_LINK 0
#endif
#if PILLOW_LINK == 0
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#else
#include <PillowRadio.h>  // radio only: Bluetooth and ESP-NOW together are unreliable
#endif

// Board pins (Waveshare pin_config.h + schematic)
#define IIC_SDA 15
#define IIC_SCL 14
#define I2S_MCK 16
#define I2S_BCK 9
#define I2S_WS 45
#define I2S_DOUT 8   // ESP32 -> codec DSDIN (speaker)
#define I2S_DIN 10   // codec ASDOUT -> ESP32 (mic)
#define PA_EN 46     // NS4150B speaker amplifier enable
#define QMI8658_ADDR 0x6B
#define UNO_RX 44    // header pad U0RXD <- Uno pin 1 (TX) via 1k/2k divider; Uno GND to GND
#define UNO_TX 43    // header pad U0TXD, unused (leave unwired: the ROM boot log comes out here)

// GATT UUIDs: shared with sim/audio_bridge.py
#define SERVICE_UUID "6e9d0001-5a1c-4c5e-9b7e-70696c6c6f77"
#define MIC_UUID     "6e9d0002-5a1c-4c5e-9b7e-70696c6c6f77"
#define SPK_UUID     "6e9d0003-5a1c-4c5e-9b7e-70696c6c6f77"
#define CTRL_UUID    "6e9d0004-5a1c-4c5e-9b7e-70696c6c6f77"
#define EVENT_UUID   "6e9d0005-5a1c-4c5e-9b7e-70696c6c6f77"

const int RATE = 16000;
const size_t FRAME_SAMPLES = RATE / 10;      // 100 ms, what Cartesia Ink-2 wants per frame
const size_t SPK_BUFFER = RATE * 2 * 2;      // 2 s of mono s16le
const size_t BLE_CHUNK_MAX = 240;            // mu-law bytes per notification (fits a 247 MTU)
const uint32_t PA_OFF_AFTER_MS = 400;        // amp off when idle: no hiss next to a sleeping ear
const float TAP_G = 0.45;                    // accel jump (g) between samples = a squeeze/tap
const int MIC_SLOT = 0;                      // stereo slot with the ES8311 ADC (verified: left)
const uint32_t UNO_BAUD = 9600;              // match the Uno sketch's Serial.begin()
const size_t UNO_LINE_MAX = 200;

I2SClass i2s;
es8311_handle_t codec;
StreamBufferHandle_t speaker;
volatile bool micSerial = false, micLink = false;  // mic asked for over USB / the wireless link
volatile uint32_t lastPlayMs = 0;
bool imuOk = false;

#if PILLOW_LINK == 0
volatile bool bleConnected = false;
BLEServer *server;
BLECharacteristic *micChar, *eventChar;
bool linkUp() { return bleConnected; }

// ---------- G.711 mu-law ----------
uint8_t ulawEncode(int16_t sample) {
  int sign = sample < 0 ? 0x80 : 0;
  int v = min(abs((int)sample), 32635) + 0x84;
  int exponent = 7;
  for (int mask = 0x4000; !(v & mask) && exponent > 0; mask >>= 1) exponent--;
  return ~(sign | (exponent << 4) | ((v >> (exponent + 3)) & 0x0F));
}

int16_t ulawDecode(uint8_t u) {
  u = ~u;
  int v = ((((u & 0x0F) << 3) + 0x84) << ((u >> 4) & 7)) - 0x84;
  return (u & 0x80) ? -v : v;
}
#else
using radio::ulawDecode;
using radio::ulawEncode;
bool linkUp() { return radio::paired; }
#endif

// ---------- codec ----------
bool codecInit() {
  codec = es8311_create(0, ES8311_ADDRESS_0);
  if (!codec) return false;
  const es8311_clock_config_t clk = {
    .mclk_inverted = false, .sclk_inverted = false, .mclk_from_mclk_pin = true,
    .mclk_frequency = RATE * 256, .sample_frequency = RATE};
  return es8311_init(codec, &clk, ES8311_RESOLUTION_16, ES8311_RESOLUTION_16) == ESP_OK &&
         es8311_sample_frequency_config(codec, clk.mclk_frequency, RATE) == ESP_OK &&
         es8311_microphone_config(codec, false) == ESP_OK &&  // analog mic, not PDM
         es8311_voice_volume_set(codec, 75, NULL) == ESP_OK &&
         es8311_microphone_gain_set(codec, (es8311_mic_gain_t)4) == ESP_OK;  // +24 dB: muffled by the pillow
}

// ---------- audio tasks ----------
// Speaker: drain the stream buffer into I2S (mono -> both slots); write silence when empty so the
// DMA never replays a stale buffer.
void speakerTask(void *) {
  static int16_t mono[256], stereo[512];
  for (;;) {
    size_t got = xStreamBufferReceive(speaker, mono, sizeof(mono), pdMS_TO_TICKS(10));
    size_t n = got / 2;
    if (n) {
      lastPlayMs = millis();
      digitalWrite(PA_EN, HIGH);
    } else {
      n = 160;  // 10 ms of silence
      memset(mono, 0, n * 2);
      if (millis() - lastPlayMs > PA_OFF_AFTER_MS) digitalWrite(PA_EN, LOW);
    }
    for (size_t i = 0; i < n; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
    i2s.write((uint8_t *)stereo, n * 4);
  }
}

void sendMicLink(const int16_t *mono) {
  static uint8_t ulaw[FRAME_SAMPLES];
  for (size_t i = 0; i < FRAME_SAMPLES; i++) ulaw[i] = ulawEncode(mono[i]);
#if PILLOW_LINK == 0
  size_t chunk = min(BLE_CHUNK_MAX, (size_t)server->getPeerMTU(server->getConnId()) - 3);
  for (size_t i = 0; i < FRAME_SAMPLES; i += chunk) {
    micChar->setValue(ulaw + i, min(chunk, FRAME_SAMPLES - i));
    micChar->notify();
  }
#else
  for (size_t i = 0; i < FRAME_SAMPLES; i += radio::AUDIO_CHUNK)
    radio::send(radio::PKT_MIC, ulaw + i, min(radio::AUDIO_CHUNK, FRAME_SAMPLES - i));
#endif
}

void sendMicSerial(const int16_t *mono) {
  static unsigned char b64[((FRAME_SAMPLES * 2 + 2) / 3) * 4 + 1];
  size_t len = 0;
  if (mbedtls_base64_encode(b64, sizeof(b64), &len, (const unsigned char *)mono, FRAME_SAMPLES * 2)) return;
  b64[len] = 0;
  Serial.print("MIC ");
  Serial.println((char *)b64);
}

// Mic: read 100 ms stereo frames, keep the ADC slot, send it wherever the mic was asked for.
void micTask(void *) {
  static int16_t stereo[FRAME_SAMPLES * 2], mono[FRAME_SAMPLES];
  for (;;) {
    size_t got = i2s.readBytes((char *)stereo, sizeof(stereo));
    bool toLink = micLink && linkUp();
    if (got < sizeof(stereo) || !(micSerial || toLink)) continue;
    for (size_t i = 0; i < FRAME_SAMPLES; i++) mono[i] = stereo[2 * i + MIC_SLOT];
    if (toLink) sendMicLink(mono);
    if (micSerial) sendMicSerial(mono);
  }
}

// ---------- commands (both links) ----------
void handleCommand(const String &cmd, bool fromLink) {
  volatile bool &mic = fromLink ? micLink : micSerial;
  if (cmd == "MIC ON") {
    mic = true;
  } else if (cmd == "MIC OFF") {
    mic = false;
  } else if (cmd.startsWith("VOL ")) {
    es8311_voice_volume_set(codec, constrain(cmd.substring(4).toInt(), 0, 100), NULL);
  } else if (cmd.startsWith("GAIN ")) {
    es8311_microphone_gain_set(codec, (es8311_mic_gain_t)constrain(cmd.substring(5).toInt(), 0, 7));
  }
}

// A short text message over the wireless link: "talk", or "UNO <line>"
void sendLinkText(const char *text, bool isTalk) {
  if (!linkUp()) return;
#if PILLOW_LINK == 0
  eventChar->setValue((uint8_t *)text, min(strlen(text), BLE_CHUNK_MAX));
  eventChar->notify();
#else
  radio::sendText(isTalk ? radio::PKT_EVENT : radio::PKT_LINE, text);
#endif
}

void talkEvent() {
  Serial.println("KEY talk");
  sendLinkText("talk", true);
}

#if PILLOW_LINK == 0
// ---------- BLE ----------
class ServerEvents : public BLEServerCallbacks {
  void onConnect(BLEServer *s, ble_gap_conn_desc *desc) override {
    bleConnected = true;
    // Ask for a 7.5-15 ms connection interval: the mic sends ~70 notifications a second, too many
    // for the 30-50 ms laptops pick by default. Units 1.25 ms; supervision timeout units 10 ms.
    s->updateConnParams(desc->conn_handle, 6, 12, 0, 400);
    Serial.println("ble: connected");
  }
  void onDisconnect(BLEServer *) override {
    bleConnected = false;
    micLink = false;
    Serial.println("ble: disconnected, advertising");
    BLEDevice::startAdvertising();
  }
};

class SpeakerWrites : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    static int16_t pcm[BLE_CHUNK_MAX + 16];
    size_t n = min(c->getLength(), sizeof(pcm) / 2);
    const uint8_t *ulaw = c->getData();
    for (size_t i = 0; i < n; i++) pcm[i] = ulawDecode(ulaw[i]);
    xStreamBufferSend(speaker, pcm, n * 2, pdMS_TO_TICKS(20));
  }
};

class ControlWrites : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    handleCommand(String((const char *)c->getData(), c->getLength()), true);
  }
};

void bleInit() {
  BLEDevice::init("pillow-voice");
  BLEDevice::setMTU(247);
  server = BLEDevice::createServer();
  server->setCallbacks(new ServerEvents());
  BLEService *service = server->createService(SERVICE_UUID);
  micChar = service->createCharacteristic(MIC_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  micChar->addDescriptor(new BLE2902());
  eventChar = service->createCharacteristic(EVENT_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  eventChar->addDescriptor(new BLE2902());
  service->createCharacteristic(SPK_UUID, BLECharacteristic::PROPERTY_WRITE_NR)
      ->setCallbacks(new SpeakerWrites());
  service->createCharacteristic(CTRL_UUID, BLECharacteristic::PROPERTY_WRITE)
      ->setCallbacks(new ControlWrites());
  service->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(SERVICE_UUID);
  adv->setScanResponse(true);
  bool ok = adv->start();
  Serial.printf("ble: advertising %s, address %s\n", ok ? "started" : "FAILED", BLEDevice::getAddress().toString().c_str());
}

void linkInit() { bleInit(); }
#else
// ---------- radio (ESP-NOW or the relay's access point) ----------
// On the radio task.
void onRadio(char type, const uint8_t *data, size_t len) {
  if (type == radio::PKT_HELLO) {
    micLink = data[0] & 1;  // the relay's hellos carry the mic state: survives our reboot
  } else if (type == radio::PKT_SPK) {
    static int16_t pcm[radio::MAX_PACKET];
    for (size_t i = 0; i < len; i++) pcm[i] = ulawDecode(data[i]);
    xStreamBufferSend(speaker, pcm, len * 2, pdMS_TO_TICKS(50));
  } else if (type == radio::PKT_CMD) {
    handleCommand(String((const char *)data, len), true);
  }
}

void linkInit() {
  bool ok = radio::begin(PILLOW_LINK, false, onRadio);
  Serial.printf("radio: %s %s, channel %d, mac %s\n", PILLOW_LINK == LINK_WIFI ? "joining hidden access point" : "esp-now",
                ok ? "started" : "FAILED", RADIO_CHANNEL, WiFi.macAddress().c_str());
}
#endif

// ---------- Uno passthrough ----------
void readUno() {
  static String line;
  static bool garbled = false;  // wrong baud or a floating pin: drop the whole line
  while (Serial1.available()) {
    char ch = Serial1.read();
    if (ch == '\r') continue;
    if (ch != '\n') {
      if (ch == '\t') ch = ' ';  // Serial.print("\t") between readings is common
      if (ch < 0x20 || ch > 0x7e) garbled = true;
      else if (line.length() < UNO_LINE_MAX) line += ch;
      continue;
    }
    if (!garbled && line.length()) {
      String out = "UNO " + line;
      Serial.println(out);
      sendLinkText(out.c_str(), false);
    }
    line = "";
    garbled = false;
  }
}

// ---------- IMU tap (QMI8658, raw registers) ----------
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
  imuOk = present && Wire.read() == 0x05;
  qmiWrite(0x02, 0x40);  // CTRL1: register address auto-increment
  qmiWrite(0x03, 0x15);  // CTRL2: accel ±4 g, ~250 Hz
  qmiWrite(0x08, 0x01);  // CTRL7: accelerometer on
}

float median3(float a, float b, float c) { return fmaxf(fminf(a, b), fminf(fmaxf(a, b), c)); }

void checkTap() {
  static float hist[3][3], lx, ly, lz;  // last 3 raw samples per axis, last filtered sample
  static int warmup = 4;
  static uint32_t quietUntil = 0;
  if (!imuOk) return;
  Wire.beginTransmission(QMI8658_ADDR);
  Wire.write(0x35);  // AX_L
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(QMI8658_ADDR, 6) != 6) return;
  int16_t raw[3];
  for (int i = 0; i < 3; i++) raw[i] = Wire.read() | (Wire.read() << 8);
  // Median of the last 3 samples: a single glitched read (the IMU isn't synced, so a read can
  // straddle an update) used to look like a 0.5-0.7 g tap every few seconds. A squeeze lasts longer.
  float f[3];
  for (int i = 0; i < 3; i++) {
    hist[i][0] = hist[i][1];
    hist[i][1] = hist[i][2];
    hist[i][2] = raw[i] / 8192.0;
    f[i] = median3(hist[i][0], hist[i][1], hist[i][2]);
  }
  float ax = f[0], ay = f[1], az = f[2];
  float change = fabs(ax - lx) + fabs(ay - ly) + fabs(az - lz);
  lx = ax; ly = ay; lz = az;
  // Ignore taps while the speaker plays and just after: the cone and the amp's off-click shake the board.
  bool playing = millis() - lastPlayMs < PA_OFF_AFTER_MS + 600;
  if (warmup == 0 && !playing && change > TAP_G && millis() > quietUntil) {
    Serial.printf("tap: %.2f g jump (a = %.2f %.2f %.2f)\n", change, ax, ay, az);
    talkEvent();
    quietUntil = millis() + 2000;  // one squeeze = one event
  }
  if (warmup > 0) warmup--;
}

// ---------- serial link ----------
void handleSerialLine(const String &line) {
  if (!line.startsWith("SPK ")) {
    handleCommand(line, false);
    return;
  }
  static unsigned char pcm[4096];
  size_t len = 0;
  if (mbedtls_base64_decode(pcm, sizeof(pcm), &len, (const unsigned char *)line.c_str() + 4,
                            line.length() - 4) == 0)
    xStreamBufferSend(speaker, pcm, len & ~1u, pdMS_TO_TICKS(200));
}

void readSerial() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') { if (line.length() < 6000) line += ch; continue; }
    handleSerialLine(line);
    line = "";
  }
}

void setup() {
  Serial.setRxBufferSize(16384);  // SPK lines arrive in bursts
  Serial.begin(115200);
  pinMode(PA_EN, OUTPUT);
  digitalWrite(PA_EN, LOW);
  Wire.begin(IIC_SDA, IIC_SCL);
  imuInit();
  i2s.setPins(I2S_BCK, I2S_WS, I2S_DOUT, I2S_DIN, I2S_MCK);
  bool i2sOk = i2s.begin(I2S_MODE_STD, RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);
  bool codecOk = i2sOk && codecInit();
  speaker = xStreamBufferCreate(SPK_BUFFER, 2);
  Serial1.begin(UNO_BAUD, SERIAL_8N1, UNO_RX, UNO_TX);
  gpio_pullup_en((gpio_num_t)UNO_RX);  // idle high when no Uno is wired: no garbage lines
  linkInit();
  Serial.printf("voice_unit: i2s %s, es8311 %s, imu %s, link %d, uno rx gpio %d @ %u\n", i2sOk ? "ok" : "FAILED",
                codecOk ? "ok" : "FAILED", imuOk ? "ok" : "missing", PILLOW_LINK, UNO_RX, (unsigned)UNO_BAUD);
  xTaskCreatePinnedToCore(speakerTask, "spk", 4096, NULL, 5, NULL, 1);
  xTaskCreatePinnedToCore(micTask, "mic", 8192, NULL, 4, NULL, 1);
}

void loop() {
  readSerial();
  readUno();
  static uint32_t lastImu = 0;
  if (millis() - lastImu >= 20) {
    lastImu = millis();
    checkTap();
  }
  delay(1);
}
