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
//   A  ack of a C or E packet: type, sequence number
//
// C and E must not get lost: they carry a sequence number after the type byte, are resent until
// the other board acks them (sendReliable), and repeats are dropped on arrival. Audio and L lines
// are sent once: a lost one is 50 ms of sound or one 500 ms sensor reading, and the next follows.
//
// LINK_ESPNOW: no access point, no beacons. Packets to the peer are encrypted (PMK + LMK from
// secrets.h); hellos go out in the clear until the boards pair. Fixed channel; 6 Mbit/s OFDM and
// 15 dBm by default (RADIO_PHY_RATE, RADIO_TX_POWER: see secrets.example.h). The 1 Mbit/s default
// rate would spend a third of the airtime on audio. Each unicast packet is also acked and retried
// by the radio itself.
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

#ifndef RADIO_PHY_MODE
#define RADIO_PHY_MODE WIFI_PHY_MODE_11G
#endif
#ifndef RADIO_PHY_RATE
#define RADIO_PHY_RATE WIFI_PHY_RATE_6M  // the sturdiest OFDM rate: ~5 dB more range than 12M
#endif
#ifndef RADIO_TX_POWER
#define RADIO_TX_POWER WIFI_POWER_15dBm  // a body between the boards eats 10+ dB at 2.4 GHz
#endif

#define LINK_BLE 0
#define LINK_ESPNOW 1
#define LINK_WIFI 2

namespace radio {

const char PKT_HELLO = 'H', PKT_MIC = 'M', PKT_SPK = 'S', PKT_CMD = 'C', PKT_EVENT = 'E', PKT_LINE = 'L',
           PKT_ACK = 'A';
const size_t MAX_PACKET = ESP_NOW_MAX_DATA_LEN_V2;
const size_t RX_QUEUE = 24;  // ~36 KB: half a second of audio both ways if the radio task stalls
const int RELIABLE_TRIES = 6;
const uint32_t ACK_WAIT_MS = 60;
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
// Counters for printStats()
inline volatile uint32_t sendFails = 0, rxPackets = 0, rxDrops = 0, reliableLost = 0;
inline volatile int8_t lastRssi = 0;

// Reliable sends (C, E): one at a time, the radio task signals the ack
inline SemaphoreHandle_t ackSem = nullptr, reliableLock = nullptr;
inline volatile char ackWaitType = 0;
inline volatile uint8_t ackWaitSeq = 0;
inline uint8_t txSeq = 0;
inline int16_t rxSeqCmd = -1, rxSeqEvent = -1;  // last sequence number seen per reliable type

// Log lines from the radio task. The relay routes them through its USB lock (whole lines only).
inline void (*logHook)(const char *line) = nullptr;
inline void logLine(const char *fmt, ...) {
  char line[160];
  va_list args;
  va_start(args, fmt);
  vsnprintf(line, sizeof(line), fmt, args);
  va_end(args);
  if (logHook) logHook(line);
  else Serial.println(line);
}

inline void queuePacket(const uint8_t *data, size_t len, const uint8_t *from, bool broadcast, uint32_t ip) {
  static Packet p;  // only ever called from one task: the Wi-Fi task (ESP-NOW) or AsyncUDP's
  if (!rx || len < 1 || len > MAX_PACKET) return;
  p.len = len;
  p.broadcast = broadcast;
  memcpy(p.from, from ? from : BROADCAST, 6);
  p.ip = ip;
  memcpy(p.data, data, len);
  rxPackets++;
  if (xQueueSend(rx, &p, 0) != pdTRUE) rxDrops++;  // full: the radio task is stuck behind
}

inline void onNowRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  if (info->rx_ctrl) lastRssi = info->rx_ctrl->rssi;
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

// Send a C or E packet and wait for the other board's ack, resending up to RELIABLE_TRIES times
// (~0.4 s). Blocks: never call it from the radio task (the handler), which delivers the acks.
inline bool sendReliable(char type, const uint8_t *payload, size_t len) {
  if (!paired || len + 2 > MAX_PACKET) return false;
  uint8_t buf[MAX_PACKET];
  xSemaphoreTake(reliableLock, portMAX_DELAY);
  uint8_t seq = ++txSeq;
  buf[0] = type;
  buf[1] = seq;
  memcpy(buf + 2, payload, len);
  xSemaphoreTake(ackSem, 0);  // clear a late ack from the last message
  ackWaitType = type;
  ackWaitSeq = seq;
  bool acked = false;
  for (int i = 0; i < RELIABLE_TRIES && !acked && paired; i++) {
    sendRaw(buf, len + 2, false);
    acked = xSemaphoreTake(ackSem, pdMS_TO_TICKS(ACK_WAIT_MS)) == pdTRUE;
  }
  ackWaitType = 0;
  xSemaphoreGive(reliableLock);
  if (!acked) {
    reliableLost++;
    logLine("radio: no ack for a '%c' packet after %d tries", type, RELIABLE_TRIES);
  }
  return acked;
}

inline bool sendReliableText(char type, const char *text) {
  return sendReliable(type, (const uint8_t *)text, strlen(text));
}

// One line of link health, for the bench test
inline void formatStats(char *out, size_t n) {
  snprintf(out, n, "radio: %s, rssi %d dBm, %u packets in, %u queue drops, %u send fails, %u control msgs lost",
           paired ? "paired" : "NOT paired", lastRssi, (unsigned)rxPackets, (unsigned)rxDrops, (unsigned)sendFails,
           (unsigned)reliableLost);
}

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
  esp_now_rate_config_t rate = {.phymode = RADIO_PHY_MODE, .rate = RADIO_PHY_RATE, .ersu = false, .dcm = false};
  if (esp_now_set_peer_rate_config(mac, &rate) != ESP_OK) logLine("radio: couldn't set the PHY rate, using the default");
  return true;
}

inline void unpair(const char *why) {
  if (!wifiMode) esp_now_del_peer(peer);
  paired = false;
  peerIp = 0;
  logLine("radio: link lost (%s), looking for the other board", why);
}

// A hello. Unpaired: pair with whoever sent it. A hello that says its sender is unpaired (it just
// booted, or gave up on us) gets an answer in the clear at once, so both ends pair within one
// exchange; answering only those keeps two paired boards from echoing hellos at each other.
inline bool onHello(const Packet &p) {
  const size_t magic = sizeof(MAGIC) - 1;
  if (p.len != 1 + magic + 2 || memcmp(p.data + 1, MAGIC, magic) != 0) return false;
  bool senderPaired = p.data[1 + magic];
  if (!senderPaired) rxSeqCmd = rxSeqEvent = -1;  // it (re)booted: its sequence numbers start over
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
    if (wifiMode) logLine("radio: linked with %s", IPAddress(hub ? peerIp : HUB_IP).toString().c_str());
    else logLine("radio: paired with %02x:%02x:%02x:%02x:%02x:%02x", p.from[0], p.from[1], p.from[2], p.from[3], p.from[4], p.from[5]);
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

// A packet from the peer: acks wake sendReliable, C/E are acked and delivered once, the rest as is
inline void onPeerPacket(const Packet &p) {
  char type = p.data[0];
  if (type == PKT_ACK) {
    if (p.len == 3 && ackWaitType && p.data[1] == ackWaitType && p.data[2] == ackWaitSeq) xSemaphoreGive(ackSem);
    return;
  }
  if (type != PKT_CMD && type != PKT_EVENT) {
    handler(type, p.data + 1, p.len - 1);
    return;
  }
  if (p.len < 2) return;
  uint8_t seq = p.data[1];
  uint8_t ack[3] = {PKT_ACK, (uint8_t)type, seq};
  sendRaw(ack, sizeof(ack), false);
  int16_t &last = type == PKT_CMD ? rxSeqCmd : rxSeqEvent;
  if (last == seq) return;  // a resend: our ack got lost
  last = seq;
  handler(type, p.data + 2, p.len - 2);
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
        onPeerPacket(p);
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
  WiFi.setTxPower(RADIO_TX_POWER);
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
  WiFi.setTxPower(RADIO_TX_POWER);
  return beginUdp();
}

// The relay's hidden access point (LINK_WIFI only). Not started by begin(): the relay asks for it.
inline bool startAccessPoint() {
  WiFi.mode(WIFI_AP);
  bool ok = WiFi.softAP(RADIO_AP_SSID, RADIO_AP_PASS, RADIO_CHANNEL, 1 /* hidden */, 1 /* one client */);
  WiFi.setTxPower(RADIO_TX_POWER);
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
  rx = xQueueCreate(RX_QUEUE, sizeof(Packet));
  ackSem = xSemaphoreCreateBinary();
  reliableLock = xSemaphoreCreateMutex();
  txSeq = esp_random();
  if (!ackSem || !reliableLock) return false;
  bool ok = rx && (wifiMode ? (hub ? beginUdp() : joinAccessPoint()) : beginEspNow());
  if (ok) xTaskCreatePinnedToCore(task, "radio", 8192, NULL, 3, NULL, 0);
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
