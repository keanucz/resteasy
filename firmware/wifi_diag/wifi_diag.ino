// Wi-Fi diagnostic: what 2.4 GHz networks the ESP32 sees, and why joining fails.
#include <WiFi.h>
#include "../kid_pillow/secrets.h"

void onEvent(WiFiEvent_t e, WiFiEventInfo_t info) {
  if (e == ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
    Serial.printf("DISCONNECTED reason=%d\n", info.wifi_sta_disconnected.reason);
  if (e == ARDUINO_EVENT_WIFI_STA_GOT_IP)
    Serial.printf("GOT IP %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  delay(2000);
  WiFi.mode(WIFI_STA);
  WiFi.onEvent(onEvent);
  int n = WiFi.scanNetworks();
  for (int i = 0; i < n; i++)
    Serial.printf("SCAN %-24s ch%2d rssi%4d auth%d\n", WiFi.SSID(i).c_str(), WiFi.channel(i), WiFi.RSSI(i), WiFi.encryptionType(i));
  Serial.printf("SCAN DONE %d\n", n);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 60 && WiFi.status() != WL_CONNECTED; i++) delay(250);
  Serial.printf("STATUS %d\n", WiFi.status());
}

void loop() {}
