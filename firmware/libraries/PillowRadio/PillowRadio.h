// PillowRadio: the radio link between the voice unit in the pillow (firmware/voice_unit) and the
// relay board on the laptop's USB (firmware/espnow_relay), used instead of Bluetooth when both are
// built with PILLOW_LINK = LINK_ESPNOW or LINK_WIFI. Both transports carry the same packets: one
// type byte, then the payload, at most 1470 bytes (ESP-NOW v2):
//
//   H  hello: MAGIC, "sender is paired" byte, app byte (relay -> unit: 1 = mic on). Pairs the two
//      boards and keeps the link alive: broadcast until paired, then sent to the peer every 2 s
//   M  mic audio, unit -> relay: 16 kHz G.711 mu-law
//   S  speaker audio, relay -> unit: the same
//   C  command, relay -> unit: "MIC ON", "VOL 60", ... (voice_unit's serial protocol)
//   E  event, unit -> relay: "talk"
//   L  text line, unit -> relay: the Uno's sensor lines ("UNO ...")
//
// LINK_ESPNOW: no access point, no beacons. Packets to the peer are encrypted (PMK + LMK from
// secrets.h); hellos go out in the clear until the boards pair. Fixed channel, 12 Mbit/s OFDM
// (the 1 Mbit/s default is too slow for audio both ways), low transmit power: the boards sit a
// metre apart.
// LINK_WIFI (experiment): the relay runs a hidden 2.4 GHz access point and both ends talk UDP.
// A hidden access point still transmits; it is a hotspot. Never at the venue.
//
// Build with --libraries firmware/libraries. Both boards need the same secrets.h (gitignored).

#pragma once
#include <Arduino.h>
#include <AsyncUDP.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "freertos/queue.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy firmware/libraries/PillowRadio/secrets.example.h to secrets.h (gitignored) and fill it in"
#endif

#define LINK_BLE 0
#define LINK_ESPNOW 1
#define LINK_WIFI 2

namespace radio {

const char PKT_HELLO = 'H', PKT_MIC = 'M', PKT_SPK = 'S', PKT_CMD = 'C', PKT_EVENT = 'E', PKT_LINE = 'L';
const size_t MAX_PACKET = ESP_NOW_MAX_DATA_LEN_V2;
const size_t AUDIO_CHUNK = 800;  // mu-law bytes per audio packet: 50 ms
const uint32_t HELLO_MS = 2000, LOST_MS = 6000, REPLY_GAP_MS = 500;
const uint16_t UDP_PORT = 47800;
const char MAGIC[] = "pillow-radio1";
const uint8_t BROADCAST[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
const uint32_t HUB_IP = (uint32_t)IPAddress(192, 168, 4, 1);  // the relay's access point

typedef void (*Handler)(char type, const uint8_t *data, size_t len);

struct Packet {
  uint16_t len;
  bool broadcast;
  uint8_t from[6];
  uint32_t ip;
  uint8_t data[MAX_PACKET];
};

inline bool wifiMode = false, hub = false;
inline Handler handler = nullptr;
inline QueueHandle_t rx = nullptr;
inline AsyncUDP udp;
inline uint8_t peer[6];
inline uint32_t peerIp = 0;            // LINK_WIFI: the other end (the relay learns it)
inline volatile bool paired = false;
inline volatile uint32_t lastHeardMs = 0;
inline volatile uint8_t helloApp = 0;  // the app byte in our hellos
inline volatile uint32_t sendFails = 0;

inline void queuePacket(const uint8_t *data, size_t len, const uint8_t *from, bool broadcast, uint32_t ip) {
  static Packet p;  // only ever called from one task: the Wi-Fi task (ESP-NOW) or AsyncUDP's
  if (!rx || len < 1 || len > MAX_PACKET) return;
  p.len = len;
  p.broadcast = broadcast;
  memcpy(p.from, from ? from : BROADCAST, 6);
  p.ip = ip;
  memcpy(p.data, data, len);
  xQueueSend(rx, &p, 0);  // full: drop, like a lost radio packet
}

inline void onNowRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  queuePacket(data, len, info->src_addr, memcmp(info->des_addr, BROADCAST, 6) == 0, 0);
}

inline void onNowSent(const esp_now_send_info_t *, esp_now_send_status_t status) {
  if (status != ESP_NOW_SEND_SUCCESS) sendFails++;
}

// LINK_WIFI: the relay has no address for the unit until the unit's first hello; the unit has
// none until it joins the access point.
inline bool canSend() { return !wifiMode || (hub ? peerIp != 0 : WiFi.status() == WL_CONNECTED); }

inline bool sendRaw(const uint8_t *buf, size_t len, bool toAll) {
  bool ok;
  if (wifiMode) {
    ok = canSend() && udp.writeTo(buf, len, IPAddress(hub ? peerIp : HUB_IP), UDP_PORT) == len;
  } else {
    ok = esp_now_send(toAll ? BROADCAST : peer, buf, len) == ESP_OK;
  }
  if (!ok) sendFails++;
  return ok;
}

// Send one packet to the paired board. False when not paired or the radio is busy (then dropped).
inline bool send(char type, const uint8_t *payload, size_t len) {
  if (!paired || len + 1 > MAX_PACKET) return false;
  uint8_t buf[MAX_PACKET];
  buf[0] = type;
  memcpy(buf + 1, payload, len);
  return sendRaw(buf, len + 1, false);
}

inline bool sendText(char type, const char *text) { return send(type, (const uint8_t *)text, strlen(text)); }

inline void sendHello(bool toAll) {
  if (!canSend()) return;  // not a failure: nobody to say hello to yet
  const size_t magic = sizeof(MAGIC) - 1;
  uint8_t buf[1 + magic + 2];
  buf[0] = PKT_HELLO;
  memcpy(buf + 1, MAGIC, magic);
  buf[1 + magic] = paired;
  buf[2 + magic] = helloApp;
  sendRaw(buf, sizeof(buf), toAll);
}

inline bool addPeer(const uint8_t *mac, bool encrypt) {
  esp_now_peer_info_t info = {};
  memcpy(info.peer_addr, mac, 6);
  info.channel = 0;  // the current channel
  info.ifidx = WIFI_IF_STA;
  info.encrypt = encrypt;
  if (encrypt) memcpy(info.lmk, RADIO_LMK, ESP_NOW_KEY_LEN);
  if (esp_now_add_peer(&info) != ESP_OK) return false;
  esp_now_rate_config_t rate = {.phymode = WIFI_PHY_MODE_11G, .rate = WIFI_PHY_RATE_12M, .ersu = false, .dcm = false};
  if (esp_now_set_peer_rate_config(mac, &rate) != ESP_OK) Serial.println("radio: couldn't set 12 Mbit/s, using default rate");
  return true;
}

inline void unpair(const char *why) {
  if (!wifiMode) esp_now_del_peer(peer);
  paired = false;
  peerIp = 0;
  Serial.printf("radio: link lost (%s), looking for the other board\n", why);
}

// A hello. Unpaired: pair with whoever sent it. A hello that says its sender is unpaired (it just
// booted, or gave up on us) gets an answer in the clear at once, so both ends pair within one
// exchange; answering only those keeps two paired boards from echoing hellos at each other.
inline bool onHello(const Packet &p) {
  const size_t magic = sizeof(MAGIC) - 1;
  if (p.len != 1 + magic + 2 || memcmp(p.data + 1, MAGIC, magic) != 0) return false;
  bool senderPaired = p.data[1 + magic];
  if (wifiMode) {
    if (hub) peerIp = p.ip;
  } else if (!paired) {
    if (!addPeer(p.from, true)) return false;
    memcpy(peer, p.from, 6);
  } else if (memcmp(p.from, peer, 6) != 0) {
    return false;  // another board: keep ours until it goes quiet
  }
  if (!paired) {
    paired = true;
    if (wifiMode) Serial.printf("radio: linked with %s\n", IPAddress(hub ? peerIp : HUB_IP).toString().c_str());
    else Serial.printf("radio: paired with %02x:%02x:%02x:%02x:%02x:%02x\n", p.from[0], p.from[1], p.from[2], p.from[3], p.from[4], p.from[5]);
  }
  lastHeardMs = millis();
  static uint32_t lastReplyMs = 0;
  if (!senderPaired && millis() - lastReplyMs > REPLY_GAP_MS) {
    lastReplyMs = millis();
    sendHello(true);
  }
  return true;
}

inline bool fromPeer(const Packet &p) {
  if (!paired) return false;
  if (!wifiMode) return memcmp(p.from, peer, 6) == 0;  // and decrypted with our LMK
  return !hub || p.ip == peerIp;
}

inline void task(void *) {
  static Packet p;
  uint32_t lastHelloMs = 0;
  for (;;) {
    if (xQueueReceive(rx, &p, pdMS_TO_TICKS(50)) == pdTRUE) {
      if (p.data[0] == PKT_HELLO) {
        if (onHello(p)) handler(PKT_HELLO, p.data + p.len - 1, 1);  // the app byte
      } else if (fromPeer(p)) {
        lastHeardMs = millis();
        handler(p.data[0], p.data + 1, p.len - 1);
      }
    }
    if (paired && millis() - lastHeardMs > LOST_MS) unpair("no packets for 6 s");
    if (millis() - lastHelloMs >= HELLO_MS) {
      lastHelloMs = millis();
      sendHello(!paired);
    }
  }
}

inline bool beginEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_ps(WIFI_PS_NONE);  // power save adds 100 ms gaps: audible
  if (esp_wifi_set_channel(RADIO_CHANNEL, WIFI_SECOND_CHAN_NONE) != ESP_OK) return false;
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  if (esp_now_init() != ESP_OK) return false;
  esp_now_set_pmk(RADIO_PMK);
  esp_now_register_recv_cb(onNowRecv);
  esp_now_register_send_cb(onNowSent);
  return addPeer(BROADCAST, false);
}

inline bool beginUdp() {
  if (!Network.begin()) return false;  // lwIP up before the socket: the relay's AP starts later
  udp.onPacket([](AsyncUDPPacket &pkt) {
    queuePacket(pkt.data(), pkt.length(), nullptr, false, (uint32_t)pkt.remoteIP());
  });
  return udp.listen(UDP_PORT);
}

// The unit joins the relay's hidden access point (LINK_WIFI only).
inline bool joinAccessPoint() {
  WiFi.mode(WIFI_STA);
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setAutoReconnect(true);
  WiFi.begin(RADIO_AP_SSID, RADIO_AP_PASS, RADIO_CHANNEL);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  return beginUdp();
}

// The relay's hidden access point (LINK_WIFI only). Not started by begin(): the relay asks for it.
inline bool startAccessPoint() {
  WiFi.mode(WIFI_AP);
  bool ok = WiFi.softAP(RADIO_AP_SSID, RADIO_AP_PASS, RADIO_CHANNEL, 1 /* hidden */, 1 /* one client */);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  return ok;
}

inline void stopAccessPoint() {
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_OFF);
}

// Start the link. `link` is LINK_ESPNOW or LINK_WIFI; `isHub` is true on the relay. `h` gets every
// packet from the paired board (type, payload), on the radio task.
inline bool begin(int link, bool isHub, Handler h) {
  wifiMode = link == LINK_WIFI;
  hub = isHub;
  handler = h;
  rx = xQueueCreate(8, sizeof(Packet));
  bool ok = rx && (wifiMode ? (hub ? beginUdp() : joinAccessPoint()) : beginEspNow());
  if (ok) xTaskCreatePinnedToCore(task, "radio", 6144, NULL, 3, NULL, 0);
  return ok;
}

// ---------- G.711 mu-law (the same as sim/audio_bridge.py) ----------
inline uint8_t ulawEncode(int16_t sample) {
  int sign = sample < 0 ? 0x80 : 0;
  int v = min(abs((int)sample), 32635) + 0x84;
  int exponent = 7;
  for (int mask = 0x4000; !(v & mask) && exponent > 0; mask >>= 1) exponent--;
  return ~(sign | (exponent << 4) | ((v >> (exponent + 3)) & 0x0F));
}

inline int16_t ulawDecode(uint8_t u) {
  u = ~u;
  int v = ((((u & 0x0F) << 3) + 0x84) << ((u >> 4) & 7)) - 0x84;
  return (u & 0x80) ? -v : v;
}

}  // namespace radio
