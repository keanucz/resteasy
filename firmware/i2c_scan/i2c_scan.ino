// Finds which pins carry the Waveshare ESP32-S3 AMOLED's onboard I2C bus, and what's on it.
#include <Wire.h>

const int CANDIDATES[][2] = {{15, 14}, {14, 15}, {8, 9}, {9, 8}, {47, 48}, {39, 40}, {11, 10}, {18, 17}};

const char *name(uint8_t a) {
  switch (a) {
    case 0x18: return "ES8311 audio codec";
    case 0x20: return "TCA9554 IO expander";
    case 0x34: return "AXP2101 power";
    case 0x38: return "FT3168 touch";
    case 0x15: return "CST820 touch (V2)";
    case 0x51: return "PCF85063 RTC";
    case 0x6A: case 0x6B: return "QMI8658 IMU";
    case 0x68: case 0x69: return "MPU6050";
    default: return "?";
  }
}

void setup() {
  Serial.begin(115200);
  delay(2500);
  for (auto &p : CANDIDATES) {
    Wire.end();
    if (!Wire.begin(p[0], p[1], 100000)) continue;
    int found = 0;
    for (uint8_t a = 1; a < 127; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) {
        Serial.printf("SDA=%d SCL=%d  0x%02X %s\n", p[0], p[1], a, name(a));
        found++;
      }
    }
    Serial.printf("SDA=%d SCL=%d  -> %d devices\n", p[0], p[1], found);
  }
  Serial.println("SCAN DONE");
}

void loop() {}
