// Voice unit: the Waveshare ESP32-S3-Touch-AMOLED-1.8, used as a speaker and microphone. It posts
// no state. sim/audio_bridge.py on the laptop turns it into a local speaker + mic for
// voice/voice.py, over USB serial (always on) plus one wireless link, chosen at build time with
// PILLOW_LINK:
//
//   LINK_BLE (0, default)  Bluetooth LE straight to the laptop, below
//   LINK_ESPNOW (1)        ESP-NOW to the other board, either:
//                          - the pillow node (firmware/pillow_node), with this unit at the bedside
//                            on the laptop's USB: the pillow's Uno lines and talk-key presses come
//                            in over the radio and go out on USB as "UNO <line>" / "KEY talk"
//                          - or the relay on the laptop's USB (firmware/espnow_relay), with this
//                            unit in the pillow: audio and commands over the radio
//   LINK_WIFI (2)          the relay's hidden 2.4 GHz access point + UDP. Experiment: it is a
//                          hotspot, never at the venue
//
// With LINK_ESPNOW to the pillow node, this unit can go in the pillow too and reach the laptop
// without USB, over either or both of:
//   PILLOW_HOTSPOT=1  the laptop's hidden hotspot (HOTSPOT_SSID in PillowRadio's secrets.h) on the
//                     radio's channel, then TCP to sim/audio_bridge.py --hotspot: the USB serial
//                     lines below, both ways. Preferred whenever it's up.
//   PILLOW_BLE=1      Bluetooth LE to the laptop, as LINK_BLE: the fallback when the hotspot is down.
// Lines for the laptop (talk, UNO, IMU) go out on USB and on one of these: the hotspot if it's up,
// else Bluetooth. Audio goes wherever the mic was asked for.
//
// The radio links carry the same audio and commands: firmware/libraries/PillowRadio.
//
// Bluetooth LE: peripheral "pillow-voice", one GATT service. Audio is 16 kHz G.711 mu-law
// (8 bits a sample, 128 kbit/s), small enough for BLE with room to spare.
//   MIC   notify  mic audio, only while the mic is on
//   SPK   write   audio to play (write without response; the bridge paces it to real time)
//   CTRL  write   text: "MIC ON", "MIC OFF", "VOL <0-100>", "GAIN <0-7>" (mic gain, 6 dB steps),
//                 "BUZZ <chime|alert> <1-3>" (below)
//   EVENT notify  "talk": a squeeze/tap of the pillow (IMU jump), "I want to say something";
//                 or "UNO <line>", a line from the Uno; or "IMU <json>" (below)
//
// USB serial (fallback, when the board is plugged into the laptop): the same as text lines.
//   board -> laptop:  MIC <base64 of 100 ms 16 kHz mono s16le>,  KEY talk,  UNO <line>,  IMU <json>,
//                     boot log
//   laptop -> board:  SPK <base64 s16le>,  MIC ON|OFF,  VOL n,  GAIN n,  BUZZ <pattern> <repeat>,
//                     LIGHT <0-100> <warm|amber|off> <fade_s>
//
// IMU: every 500 ms, "IMU {"ax":..,"ay":..,"az":.. (g), "gx":..,"gy":..,"gz":.. (deg/s),
// "motion":0.12}". motion is the contract's restlessness (coord/CONTRACT.md 1): the share of the last
// 10 s the pillow was moving, 0..1, null while the speaker has shaken the board the whole time. The
// pillow node has no IMU, so sim/audio_bridge.py puts this into the node's state when its motion is
// null.
//
// BUZZ: the server's `buzz` command (coord/CONTRACT.md 3; sounds in firmware/libraries/PillowBuzz),
// made here, not streamed. With PILLOW_LINK=1 and a pillow node that says (in its hellos) it has a
// buzzer, it goes on to the pillow and the buzzer plays it; otherwise this unit's speaker does.
//
// LIGHT: the server's `set_light` (coord/CONTRACT.md 3), e.g. Night Watch's path light. The AMOLED
// screen is the light: filled with one colour, its brightness faded. Black pixels are off, so no
// glow when dark.
//
// Uno passthrough: the Arduino Uno R3 with the pillow's sensors has no radio, so its serial output
// (pin 1, TX) comes in on UNO_RX, through a 1k/2k divider (the Uno is 5 V, the S3 3.3 V). Each line
// goes on over the wireless link and USB as "UNO <line>", unchanged.
//
// Build: arduino-cli compile --fqbn esp32:esp32:esp32s3:CDCOnBoot=cdc --libraries firmware/libraries firmware/voice_unit
//   needs the "GFX Library for Arduino" library (Arduino_GFX), as firmware/kid_pillow does
//   radio: add --build-property compiler.cpp.extra_flags=-DPILLOW_LINK=1
//   in the pillow: --build-property "compiler.cpp.extra_flags=-DPILLOW_LINK=1 -DPILLOW_HOTSPOT=1 -DPILLOW_BLE=1"
//     and --build-property build.partitions=huge_app --build-property upload.maximum_size=3145728
//     (Bluetooth + Wi-Fi don't fit the default 1.25 MB app partition), and the fqbn
//     esp32:esp32:esp32s3:CDCOnBoot=cdc,PSRAM=opi (with Bluetooth too, internal RAM runs out)
// Codec driver es8311.* is Espressif's (Apache-2.0), as shipped in Waveshare's 15_ES8311 example.

#include <Wire.h>
#include <ESP_I2S.h>
#include "driver/gpio.h"
#include "mbedtls/base64.h"
#include "freertos/stream_buffer.h"
#include "esp_heap_caps.h"
#include "es8311.h"
#include <PillowBuzz.h>
#include <Arduino_GFX_Library.h>

#ifndef PILLOW_LINK
#define PILLOW_LINK 0
#endif
#ifndef PILLOW_HOTSPOT
#define PILLOW_HOTSPOT 0
#endif
#ifndef PILLOW_BLE
#define PILLOW_BLE 0
#endif
#if (PILLOW_HOTSPOT || PILLOW_BLE) && PILLOW_LINK != 1
#error "PILLOW_HOTSPOT and PILLOW_BLE go with PILLOW_LINK=1 (ESP-NOW to the pillow node)"
#endif
#define HAS_BLE (PILLOW_LINK == 0 || PILLOW_BLE)
#define HAS_RADIO (PILLOW_LINK != 0)
#if HAS_BLE
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#endif
#if HAS_RADIO
#include <PillowRadio.h>  // with Bluetooth too (PILLOW_BLE), they share the radio: expect a lossier link
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
// AMOLED (CO5300, 368x448) on QSPI: CS 12, SCK 11, SDIO0-3 = 4-7 (as firmware/kid_pillow)

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
const float CHIME_LEVEL = 0.25, ALERT_LEVEL = 0.35;  // of full scale: soft, it plays in a bedroom at night
const uint8_t HELLO_HAS_BUZZER = 2;          // bit in the pillow node's hellos (firmware/pillow_node)
const size_t BUZZ_CMD_MAX = 24;
const uint16_t LIGHT_WARM = 0xFDAC, LIGHT_AMBER = 0xFBC0, LIGHT_BLACK = 0x0000;  // RGB565
const uint32_t LIGHT_STEP_MS = 20;
const uint32_t IMU_SAMPLE_MS = 20, IMU_REPORT_MS = 500;
const int MOTION_BUCKETS = 20;               // x IMU_REPORT_MS = the contract's 10 s
const float MOVE_G = 0.03, MOVE_DPS = 15;    // off its resting tilt, or turning: the pillow is moving
const float REST_ALPHA = 0.02;               // resting tilt: ~1 s average at IMU_SAMPLE_MS

I2SClass i2s;
es8311_handle_t codec;
StreamBufferHandle_t speaker;
SemaphoreHandle_t speakerLock;  // a stream buffer takes one writer at a time: speech links + buzz
QueueHandle_t buzzQueue;        // "BUZZ ..." commands for buzzTask
volatile bool pillowBuzzer = false;  // the paired pillow node has a buzzer
// Where a command came from; the mic streams to each source that asked for it
enum Source : uint8_t { FROM_USB, FROM_RADIO, FROM_BLE, FROM_HOTSPOT, SOURCES };
volatile bool micOn[SOURCES] = {};
volatile uint32_t lastPlayMs = 0;
bool imuOk = false;

Arduino_DataBus *displayBus = new Arduino_ESP32QSPI(12 /*CS*/, 11 /*SCK*/, 4, 5, 6, 7 /*SDIO0-3*/);
Arduino_CO5300 *gfx = new Arduino_CO5300(displayBus, GFX_NOT_DEFINED, 0, 368, 448, 16, 0, 0, 0);
bool screenOk = false;
// The light asked for; set by handleCommand (any task), drawn by updateLight in loop()
volatile uint8_t lightTarget = 0;  // brightness 0-255
volatile uint16_t lightColour = LIGHT_WARM;
volatile uint32_t lightFadeMs = 0;
volatile bool lightChanged = false;

volatile bool bleConnected = false;
#if HAS_BLE
BLEServer *server;
BLECharacteristic *micChar, *eventChar;
#endif
#if PILLOW_HOTSPOT
volatile bool hotspotConnected = false;
#else
const bool hotspotConnected = false;
#endif

#if !HAS_RADIO
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
#endif

bool radioUp() {
#if HAS_RADIO
  return radio::paired;
#else
  return false;
#endif
}

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
         es8311_voice_volume_set(codec, 85, NULL) == ESP_OK &&  // above ~90 the speaker distorts
         es8311_microphone_gain_set(codec, (es8311_mic_gain_t)4) == ESP_OK;  // +24 dB: muffled by the pillow
}

// ---------- audio tasks ----------
// Queue audio for the speaker. Every writer goes through here: the stream buffer allows one at a time.
size_t speakerWrite(const void *pcm, size_t bytes, TickType_t wait) {
  if (xSemaphoreTake(speakerLock, wait) != pdTRUE) return 0;
  size_t sent = xStreamBufferSend(speaker, pcm, bytes, wait);
  xSemaphoreGive(speakerLock);
  return sent;
}

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

// One USB / hotspot line (with its \r\n) to the hotspot's TCP queue; below
void hotspotSend(const void *line, size_t len);

void sendMicBle(const uint8_t *ulaw) {
#if HAS_BLE
  size_t chunk = min(BLE_CHUNK_MAX, (size_t)server->getPeerMTU(server->getConnId()) - 3);
  for (size_t i = 0; i < FRAME_SAMPLES; i += chunk) {
    micChar->setValue((uint8_t *)ulaw + i, min(chunk, FRAME_SAMPLES - i));
    micChar->notify();
  }
#endif
}

void sendMicRadio(const uint8_t *ulaw) {
#if HAS_RADIO
  for (size_t i = 0; i < FRAME_SAMPLES; i += radio::AUDIO_CHUNK)
    radio::send(radio::PKT_MIC, ulaw + i, min(radio::AUDIO_CHUNK, FRAME_SAMPLES - i));
#endif
}

// USB lines go out in one write each: the mic task, loop() and the radio task all print, and one
// write is atomic (HWCDC's tx lock), so lines never interleave. println() is two writes.
// The same "MIC <base64>" line goes to the hotspot.
void sendMicLine(const int16_t *mono, bool usb, bool hotspot) {
  static unsigned char line[4 + ((FRAME_SAMPLES * 2 + 2) / 3) * 4 + 3] = "MIC ";
  size_t len = 0;
  if (mbedtls_base64_encode(line + 4, sizeof(line) - 6, &len, (const unsigned char *)mono, FRAME_SAMPLES * 2)) return;
  memcpy(line + 4 + len, "\r\n", 2);
  if (usb) Serial.write(line, 4 + len + 2);
  if (hotspot) hotspotSend(line, 4 + len + 2);
}

// Mic: read 100 ms stereo frames, keep the ADC slot, send it wherever the mic was asked for.
void micTask(void *) {
  static int16_t stereo[FRAME_SAMPLES * 2], mono[FRAME_SAMPLES];
  static uint8_t ulaw[FRAME_SAMPLES];
  for (;;) {
    size_t got = i2s.readBytes((char *)stereo, sizeof(stereo));
    bool usb = micOn[FROM_USB], toRadio = micOn[FROM_RADIO] && radioUp();
    bool toBle = micOn[FROM_BLE] && bleConnected, toHotspot = micOn[FROM_HOTSPOT] && hotspotConnected;
    if (got < sizeof(stereo) || !(usb || toRadio || toBle || toHotspot)) continue;
    for (size_t i = 0; i < FRAME_SAMPLES; i++) mono[i] = stereo[2 * i + MIC_SLOT];
    if (toRadio || toBle) {
      for (size_t i = 0; i < FRAME_SAMPLES; i++) ulaw[i] = ulawEncode(mono[i]);
      if (toRadio) sendMicRadio(ulaw);
      if (toBle) sendMicBle(ulaw);
    }
    if (usb || toHotspot) sendMicLine(mono, usb, toHotspot);
  }
}

// ---------- commands (every link) ----------
void handleCommand(const String &cmd, Source from) {
  if (cmd == "MIC ON") {
    micOn[from] = true;
  } else if (cmd == "MIC OFF") {
    micOn[from] = false;
  } else if (cmd.startsWith("VOL ")) {
    es8311_voice_volume_set(codec, constrain(cmd.substring(4).toInt(), 0, 100), NULL);
  } else if (cmd.startsWith("GAIN ")) {
    es8311_microphone_gain_set(codec, (es8311_mic_gain_t)constrain(cmd.substring(5).toInt(), 0, 7));
  } else if (cmd.startsWith("BUZZ ")) {
    char text[BUZZ_CMD_MAX] = {};
    cmd.substring(0, BUZZ_CMD_MAX - 1).toCharArray(text, BUZZ_CMD_MAX);
    if (xQueueSend(buzzQueue, text, 0) != pdTRUE) Serial.print("buzz: busy, dropped\r\n");
  } else if (cmd.startsWith("LIGHT ")) {
    setLight(cmd.substring(6));
  }
}

// ---------- light ----------
// "<pct> <warm|amber|off> <fade_s>" from LIGHT; updateLight draws it.
void setLight(const String &args) {
  int a = args.indexOf(' '), b = args.indexOf(' ', a + 1);
  String colour = args.substring(a + 1, b < 0 ? args.length() : b);
  if (a < 0 || (colour != "warm" && colour != "amber" && colour != "off")) {
    Serial.printf("light: bad command '%s'\r\n", args.c_str());
    return;
  }
  int pct = colour == "off" ? 0 : constrain(args.substring(0, a).toInt(), 0, 100);
  lightColour = colour == "amber" ? LIGHT_AMBER : LIGHT_WARM;
  lightTarget = pct * 255 / 100;
  lightFadeMs = b < 0 ? 0 : constrain(args.substring(b + 1).toInt(), 0, 60) * 1000UL;
  lightChanged = true;
  Serial.printf("light: %d%% %s over %u ms\r\n", pct, colour.c_str(), (unsigned)lightFadeMs);
}

// Fades the screen's brightness toward lightTarget, one step every LIGHT_STEP_MS. The display is only
// drawn from here (loop()), never from the radio or BLE callbacks.
void updateLight() {
  static float level = 0, step = 0;
  static uint16_t shown = LIGHT_BLACK;
  static uint32_t last = 0;
  if (!screenOk || millis() - last < LIGHT_STEP_MS) return;
  last = millis();
  if (lightChanged) {
    lightChanged = false;
    step = fabsf(lightTarget - level) / max(1.0f, lightFadeMs / (float)LIGHT_STEP_MS);
    if (lightTarget > 0 && shown != lightColour) {
      shown = lightColour;
      gfx->fillScreen(shown);
    }
  }
  float target = lightTarget;
  if (level == target) return;
  level = fabsf(target - level) <= step ? target : level + (target > level ? step : -step);
  gfx->setBrightness((uint8_t)level);
  if (level == 0 && shown != LIGHT_BLACK) {
    shown = LIGHT_BLACK;
    gfx->fillScreen(LIGHT_BLACK);
  }
}

// ---------- buzz ----------
// One note as a sine wave into the speaker, 10 ms at a time. Bell notes fade out; every note fades
// in and out over 10 ms so there are no clicks.
void renderNote(const buzz::Note &note, bool bell, float level) {
  static int16_t pcm[RATE / 100];
  const size_t total = (size_t)RATE * note.ms / 1000, edge = RATE / 100;
  const float step = 2 * PI * note.hz / RATE;
  float phase = 0;
  for (size_t done = 0; done < total;) {
    size_t n = min(total - done, sizeof(pcm) / 2);
    for (size_t i = 0; i < n; i++, done++) {
      float env = bell ? expf(-4.0f * done / RATE) : 1.0f;
      env *= min(1.0f, min((float)done / edge, (float)(total - 1 - done) / edge));
      pcm[i] = note.hz ? (int16_t)(sinf(phase) * level * env * 32767) : 0;
      phase += step;
      if (phase > 2 * PI) phase -= 2 * PI;
    }
    while (xStreamBufferSpacesAvailable(speaker) < n * 2) vTaskDelay(pdMS_TO_TICKS(5));
    speakerWrite(pcm, n * 2, portMAX_DELAY);
  }
}

void playBuzz(const buzz::Pattern &pattern, int repeat) {
  float level = pattern.bell ? CHIME_LEVEL : ALERT_LEVEL;
  for (int r = 0; r < repeat; r++) {
    if (r) renderNote({0, buzz::REPEAT_GAP_MS}, false, 0);
    for (size_t i = 0; i < pattern.count; i++) renderNote(pattern.notes[i], pattern.bell, level);
  }
}

// Its own task: a buzz takes 1-4 s, and sending it to the pillow waits for an ack, which the radio
// task (one source of commands) must never do.
void buzzTask(void *) {
  char text[BUZZ_CMD_MAX];
  for (;;) {
    if (xQueueReceive(buzzQueue, text, portMAX_DELAY) != pdTRUE) continue;
    buzz::Pattern pattern;
    int repeat;
    if (!buzz::parse(String(text), pattern, repeat)) {
      Serial.printf("buzz: bad command '%s'\r\n", text);
      continue;
    }
#if HAS_RADIO
    if (radio::paired && pillowBuzzer) {
      char out[BUZZ_CMD_MAX];
      snprintf(out, sizeof(out), "BUZZ %s %d", pattern.bell ? "chime" : "alert", repeat);
      if (radio::sendReliableText(radio::PKT_CMD, out)) {
        Serial.printf("buzz: %s, on the pillow's buzzer\r\n", out);
        continue;
      }
      Serial.print("buzz: the pillow didn't ack, playing it here\r\n");
    }
#endif
    Serial.printf("buzz: %s x%d on the speaker\r\n", pattern.bell ? "chime" : "alert", repeat);
    playBuzz(pattern, repeat);
  }
}

// A USB line ("KEY talk", "UNO <line>", "IMU <json>", no \r\n) for the laptop, besides USB: on the
// hotspot if it's up, else Bluetooth (EVENT; "KEY talk" is "talk" there). Never blocks: the radio
// task calls it.
void toLaptop(const char *line) {
#if PILLOW_HOTSPOT
  if (hotspotConnected) {
    char out[256];
    int n = snprintf(out, sizeof(out), "%s\r\n", line);
    if (n > 0 && n < (int)sizeof(out)) hotspotSend(out, n);
    return;
  }
#endif
#if HAS_BLE
  if (!bleConnected) return;
  const char *text = strcmp(line, "KEY talk") == 0 ? "talk" : line;
  eventChar->setValue((uint8_t *)text, min(strlen(text), BLE_CHUNK_MAX));
  eventChar->notify();
#endif
}

// A short text message to the other board, if paired: "talk", or "UNO <line>"
void toRadio(const char *text, bool isTalk) {
#if HAS_RADIO
  if (!radio::paired) return;
  if (isTalk) radio::sendReliableText(radio::PKT_EVENT, text);  // acked and resent: never lost
  else radio::sendText(radio::PKT_LINE, text);  // a sensor snapshot: the next one is 500 ms away
#endif
}

void talkEvent() {
  Serial.print("KEY talk\r\n");
  toLaptop("KEY talk");
  toRadio("talk", true);
}

#if HAS_BLE
// ---------- BLE ----------
void bleAdvertise(bool on) {
  if (on) BLEDevice::startAdvertising();
  else BLEDevice::stopAdvertising();
}

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
    micOn[FROM_BLE] = false;
    Serial.println("ble: disconnected");
    bleAdvertise(!hotspotConnected);
  }
};

class SpeakerWrites : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    static int16_t pcm[BLE_CHUNK_MAX + 16];
    size_t n = min(c->getLength(), sizeof(pcm) / 2);
    const uint8_t *ulaw = c->getData();
    for (size_t i = 0; i < n; i++) pcm[i] = ulawDecode(ulaw[i]);
    speakerWrite(pcm, n * 2, pdMS_TO_TICKS(20));
  }
};

class ControlWrites : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    handleCommand(String((const char *)c->getData(), c->getLength()), FROM_BLE);
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
#else
void bleAdvertise(bool) {}
#endif

#if HAS_RADIO
// ---------- radio (ESP-NOW or the relay's access point) ----------
// On the radio task.
void onRadio(char type, const uint8_t *data, size_t len) {
  if (type == radio::PKT_HELLO) {
    micOn[FROM_RADIO] = data[0] & 1;  // the relay's hellos carry the mic state: survives our reboot
    pillowBuzzer = data[0] & HELLO_HAS_BUZZER;  // the pillow node's carry "I have a buzzer"
  } else if (type == radio::PKT_SPK) {
    static int16_t pcm[radio::MAX_PACKET];
    for (size_t i = 0; i < len; i++) pcm[i] = ulawDecode(data[i]);
    speakerWrite(pcm, len * 2, pdMS_TO_TICKS(50));
  } else if (type == radio::PKT_CMD) {
    handleCommand(String((const char *)data, len), FROM_RADIO);
  } else if (type == radio::PKT_LINE) {
    static char line[radio::MAX_PACKET + 3];  // the pillow node's "UNO <line>"
    memcpy(line, data, len);
    memcpy(line + len, "\r\n", 3);
    Serial.write(line, len + 2);
    line[len] = 0;
    toLaptop(line);
  } else if (type == radio::PKT_EVENT && len == 4 && memcmp(data, "talk", 4) == 0) {
    // the pillow's talk key (not talkEvent(): never send on the radio from this task)
    Serial.print("KEY talk\r\n");
    toLaptop("KEY talk");
  }
}

void logLine(const char *line) { Serial.printf("%s\r\n", line); }

void radioInit() {
  radio::logHook = logLine;
  bool ok = radio::begin(PILLOW_LINK, false, onRadio);
  Serial.printf("radio: %s %s, channel %d, mac %s\n", PILLOW_LINK == LINK_WIFI ? "joining hidden access point" : "esp-now",
                ok ? "started" : "FAILED", RADIO_CHANNEL, WiFi.macAddress().c_str());
}
#endif

void handleTextLine(const String &line, Source from);

// Big stream buffers go in PSRAM when the board has it (build with PSRAM=opi): Wi-Fi plus Bluedroid
// need most of the internal RAM, and with these 80 KB there too the BLE controller fails to start.
StreamBufferHandle_t streamInPsram(size_t size, size_t trigger) {
  uint8_t *store = (uint8_t *)heap_caps_malloc(size + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  StaticStreamBuffer_t *meta = (StaticStreamBuffer_t *)heap_caps_malloc(sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL);
  if (!store || !meta) {
    free(store);
    free(meta);
    return xStreamBufferCreate(size, trigger);
  }
  return xStreamBufferCreateStatic(size, trigger, store, meta);
}

// ---------- the laptop's hotspot ----------
#if PILLOW_HOTSPOT
// Joins the laptop's hidden access point and dials sim/audio_bridge.py --hotspot over TCP; the lines
// are the USB ones, both ways. ESP-NOW shares the radio, so the access point must be on the pillow
// node's channel (RADIO_CHANNEL). Writers queue whole lines on hotspotTx; hotspotTask alone touches
// the socket, so a slow laptop never blocks the radio task or the mic.
const uint16_t HOTSPOT_PORT = 47801;
const size_t HOTSPOT_TX_BUFFER = 16384;      // ~0.35 s of mic lines
const uint32_t HOTSPOT_RETRY_MS = 2000, HOTSPOT_CONNECT_MS = 1000;
const uint32_t HOTSPOT_HEARTBEAT_MS = 1000;  // "HB" after this long with nothing sent: the bridge drops a link silent for 5 s
WiFiClient hotspot;
StreamBufferHandle_t hotspotTx;
SemaphoreHandle_t hotspotTxLock;

// A whole line or nothing: half a line would garble the next one.
void hotspotSend(const void *line, size_t len) {
  if (!hotspotConnected || xSemaphoreTake(hotspotTxLock, pdMS_TO_TICKS(5)) != pdTRUE) return;
  if (xStreamBufferSpacesAvailable(hotspotTx) >= len) xStreamBufferSend(hotspotTx, line, len, 0);
  xSemaphoreGive(hotspotTxLock);
}

bool hotspotDial() {
  static uint32_t lastTry = 0;
  if (WiFi.status() != WL_CONNECTED || millis() - lastTry < HOTSPOT_RETRY_MS) return false;
  lastTry = millis();
  hotspot.stop();
  if (!hotspot.connect(HOTSPOT_HOST, HOTSPOT_PORT, HOTSPOT_CONNECT_MS)) return false;
  hotspot.setNoDelay(true);
  xSemaphoreTake(hotspotTxLock, portMAX_DELAY);
  xStreamBufferReset(hotspotTx);
  hotspotConnected = true;
  xSemaphoreGive(hotspotTxLock);
  bleAdvertise(false);  // advertising takes radio time from Wi-Fi: only needed while the hotspot is down
  Serial.printf("hotspot: connected to the bridge at %s:%u\r\n", HOTSPOT_HOST, HOTSPOT_PORT);
  return true;
}

void hotspotTask(void *) {
  static uint8_t buf[1460];
  static String line;
  uint32_t lastSent = 0;
  for (;;) {
    // Wi-Fi first: when the access point goes away the socket still looks connected (writes just
    // queue in lwIP) for ~30 s, and Bluetooth only advertises once we call the link lost.
    if (WiFi.status() != WL_CONNECTED || !hotspot.connected()) {
      if (hotspotConnected) {
        hotspotConnected = false;
        micOn[FROM_HOTSPOT] = false;
        hotspot.stop();
        Serial.printf("hotspot: bridge connection lost (%s)\r\n",
                      WiFi.status() != WL_CONNECTED ? "wi-fi down" : "socket closed");
        bleAdvertise(true);
      }
      if (!hotspotDial()) {
        vTaskDelay(pdMS_TO_TICKS(100));
        continue;
      }
      line = "";
    }
    int avail = hotspot.available();
    if (avail > 0) {
      int n = hotspot.read(buf, min((size_t)avail, sizeof(buf)));
      for (int i = 0; i < n; i++) {
        char ch = buf[i];
        if (ch == '\r') continue;
        if (ch != '\n') { if (line.length() < 6000) line += ch; continue; }
        handleTextLine(line, FROM_HOTSPOT);
        line = "";
      }
    }
    size_t n = xStreamBufferReceive(hotspotTx, buf, sizeof(buf), pdMS_TO_TICKS(avail > 0 ? 0 : 5));
    if (!n && millis() - lastSent >= HOTSPOT_HEARTBEAT_MS) n = sprintf((char *)buf, "HB\r\n");
    if (!n) continue;
    if (hotspot.write(buf, n) != n) hotspot.stop();
    lastSent = millis();
  }
}

void hotspotInit() {
  hotspotTx = streamInPsram(HOTSPOT_TX_BUFFER, 1);
  hotspotTxLock = xSemaphoreCreateMutex();
  WiFi.setAutoReconnect(true);
  WiFi.begin(HOTSPOT_SSID, HOTSPOT_PASS, RADIO_CHANNEL);  // hidden: needs the channel, never scans others
#if !HAS_BLE
  WiFi.setSleep(false);  // with Bluetooth on, coexistence needs modem sleep: leave it
#endif
  Serial.printf("hotspot: joining on channel %d, bridge %s:%u\r\n", RADIO_CHANNEL, HOTSPOT_HOST, HOTSPOT_PORT);
  xTaskCreatePinnedToCore(hotspotTask, "hotspot", 6144, NULL, 3, NULL, 0);
}
#else
void hotspotSend(const void *, size_t) {}
#endif

void linkInit() {
  // Wi-Fi first: with Bluedroid up first the Wi-Fi driver can't get its internal RAM and
  // esp-now fails (mac 00:00:00:00:00:00). BLE coexists fine when it starts second.
#if HAS_RADIO
  radioInit();
#endif
#if PILLOW_HOTSPOT
  hotspotInit();
#endif
#if HAS_BLE
  bleInit();
#endif
}

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
      Serial.print(out + "\r\n");
      toLaptop(out.c_str());
      toRadio(out.c_str(), false);
    }
    line = "";
    garbled = false;
  }
}

// ---------- IMU: taps and motion (QMI8658, raw registers) ----------
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
  qmiWrite(0x04, 0x45);  // CTRL3: gyro ±512 dps (64 LSB per deg/s), ~250 Hz
  qmiWrite(0x08, 0x03);  // CTRL7: accelerometer + gyro on
}

float median3(float a, float b, float c) { return fmaxf(fminf(a, b), fminf(fmaxf(a, b), c)); }

// Restlessness for the contract's motion: per IMU_REPORT_MS bucket, how many samples moved out of
// how many counted. Samples while the speaker plays aren't counted: the cone shakes the board.
struct MotionWindow {
  uint16_t moved[MOTION_BUCKETS] = {}, counted[MOTION_BUCKETS] = {};
  int now = 0;
  void add(bool moving) {
    counted[now]++;
    if (moving) moved[now]++;
  }
  float share() const {  // < 0: nothing counted in the window
    uint32_t m = 0, c = 0;
    for (int i = 0; i < MOTION_BUCKETS; i++) m += moved[i], c += counted[i];
    return c ? (float)m / c : -1;
  }
  void next() {
    now = (now + 1) % MOTION_BUCKETS;
    moved[now] = counted[now] = 0;
  }
};
MotionWindow motion;
float imuA[3], imuG[3];  // the last sample: g, deg/s

void reportImu() {
  if (!imuOk) return;
  float share = motion.share();
  char line[160], value[8] = "null";
  if (share >= 0) snprintf(value, sizeof(value), "%.2f", share);
  snprintf(line, sizeof(line), "IMU {\"ax\":%.3f,\"ay\":%.3f,\"az\":%.3f,\"gx\":%.1f,\"gy\":%.1f,\"gz\":%.1f,\"motion\":%s}",
           imuA[0], imuA[1], imuA[2], imuG[0], imuG[1], imuG[2], value);
  motion.next();
  Serial.printf("%s\r\n", line);
  toLaptop(line);
}

void readImu() {
  static float hist[3][3], lx, ly, lz;  // last 3 raw samples per axis, last filtered sample
  static float rest[3];                 // the resting tilt: a slow average of the accel
  static int warmup = 4;
  static uint32_t quietUntil = 0;
  if (!imuOk) return;
  Wire.beginTransmission(QMI8658_ADDR);
  Wire.write(0x35);  // AX_L, then AY, AZ, GX, GY, GZ
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(QMI8658_ADDR, 12) != 12) return;
  int16_t raw[6];
  for (int i = 0; i < 6; i++) raw[i] = Wire.read() | (Wire.read() << 8);
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
  float tilt = 0, turn = 0;
  for (int i = 0; i < 3; i++) {
    imuA[i] = f[i];
    imuG[i] = raw[3 + i] / 64.0;
    rest[i] = warmup > 0 ? f[i] : rest[i] + REST_ALPHA * (f[i] - rest[i]);
    tilt += fabs(f[i] - rest[i]);
    turn = fmaxf(turn, fabs(imuG[i]));
  }
  // Ignore taps while the speaker plays and just after: the cone and the amp's off-click shake the board.
  bool playing = millis() - lastPlayMs < PA_OFF_AFTER_MS + 600;
  if (warmup == 0 && !playing) motion.add(tilt > MOVE_G || turn > MOVE_DPS);
  if (warmup == 0 && !playing && change > TAP_G && millis() > quietUntil) {
    Serial.printf("tap: %.2f g jump (a = %.2f %.2f %.2f)\n", change, ax, ay, az);
    talkEvent();
    quietUntil = millis() + 2000;  // one squeeze = one event
  }
  if (warmup > 0) warmup--;
}

// ---------- serial link (and the hotspot's, the same lines) ----------
void handleTextLine(const String &line, Source from) {
  if (!line.startsWith("SPK ")) {
    handleCommand(line, from);
    return;
  }
  static unsigned char pcm[2][4096];  // one per reader: loop() (USB) and hotspotTask
  unsigned char *buf = pcm[from == FROM_HOTSPOT];
  size_t len = 0;
  if (mbedtls_base64_decode(buf, sizeof(pcm[0]), &len, (const unsigned char *)line.c_str() + 4,
                            line.length() - 4) == 0)
    speakerWrite(buf, len & ~1u, pdMS_TO_TICKS(200));
}

void readSerial() {
  static String line;
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch != '\n') { if (line.length() < 6000) line += ch; continue; }
    handleTextLine(line, FROM_USB);
    line = "";
  }
}

void setup() {
  Serial.setRxBufferSize(16384);  // SPK lines arrive in bursts
  Serial.setTxTimeoutMs(0);  // with the USB plugged in but the port closed, each write would block 100 ms
  Serial.begin(115200);
  pinMode(PA_EN, OUTPUT);
  digitalWrite(PA_EN, LOW);
  Wire.begin(IIC_SDA, IIC_SCL);
  imuInit();
  screenOk = gfx->begin();
  if (screenOk) {
    gfx->fillScreen(LIGHT_BLACK);
    gfx->setBrightness(0);
  }
  i2s.setPins(I2S_BCK, I2S_WS, I2S_DOUT, I2S_DIN, I2S_MCK);
  bool i2sOk = i2s.begin(I2S_MODE_STD, RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH);
  bool codecOk = i2sOk && codecInit();
  speaker = streamInPsram(SPK_BUFFER, 2);
  speakerLock = xSemaphoreCreateMutex();
  buzzQueue = xQueueCreate(4, BUZZ_CMD_MAX);
  Serial1.setRxBufferSize(1024);  // ~1 s at 9600 baud: loop() can wait ~0.4 s on a "talk" ack
  Serial1.begin(UNO_BAUD, SERIAL_8N1, UNO_RX, UNO_TX);
  gpio_pullup_en((gpio_num_t)UNO_RX);  // idle high when no Uno is wired: no garbage lines
  linkInit();
  Serial.printf("voice_unit: i2s %s, es8311 %s, imu %s, screen %s, link %d, hotspot %d, ble %d, uno rx gpio %d @ %u, heap %u\n",
                i2sOk ? "ok" : "FAILED", codecOk ? "ok" : "FAILED", imuOk ? "ok" : "missing",
                screenOk ? "ok" : "FAILED", PILLOW_LINK, PILLOW_HOTSPOT, HAS_BLE, UNO_RX, (unsigned)UNO_BAUD,
                (unsigned)ESP.getFreeHeap());
  xTaskCreatePinnedToCore(speakerTask, "spk", 4096, NULL, 5, NULL, 1);
  xTaskCreatePinnedToCore(micTask, "mic", 8192, NULL, 4, NULL, 1);
  xTaskCreatePinnedToCore(buzzTask, "buzz", 4096, NULL, 3, NULL, 1);
}

void loop() {
  readSerial();
  readUno();
  static uint32_t lastImu = 0, lastReport = 0;
  if (millis() - lastImu >= IMU_SAMPLE_MS) {
    lastImu = millis();
    readImu();
  }
  if (millis() - lastReport >= IMU_REPORT_MS) {
    lastReport = millis();
    reportImu();
  }
  updateLight();
  delay(1);
}
