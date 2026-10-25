#!/usr/bin/env bash
# GFX Library for Arduino 1.6.4 (and every release so far) calls spiFrequencyToClockDiv(freq), but
# esp32 core 3.3.10+ changed it to spiFrequencyToClockDiv(spi, freq), so voice_unit fails to compile.
# This adds a version-checked wrapper to the two SPI databus files. Safe to run twice.
# Usage: firmware/patch_gfx.sh [path to GFX_Library_for_Arduino]
set -euo pipefail
G=${1:-$HOME/Arduino/libraries/GFX_Library_for_Arduino}/src/databus
SPI=$G/Arduino_ESP32SPI.cpp
DMA=$G/Arduino_ESP32SPIDMA.cpp

if grep -q gfxSpiFrequencyToClockDiv "$SPI" "$DMA"; then
  echo "GFX already patched"
  exit 0
fi

wrapper='static uint32_t gfxSpiFrequencyToClockDiv(spi_t *spi, uint32_t freq)\
{\
#if defined(ESP_ARDUINO_VERSION) \&\& ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 3, 10)\
  return spiFrequencyToClockDiv(spi, freq);\
#else\
  (void)spi;\
  return spiFrequencyToClockDiv(freq);\
#endif\
}'

for f in "$SPI" "$DMA"; do
  # right after the file's ESP32 guard, before the first use
  sed -i "0,/^#if defined(ESP32)/{/^#if defined(ESP32)/a\\
$wrapper
}" "$f"
done
sed -i 's/= spiFrequencyToClockDiv(old_apb/= gfxSpiFrequencyToClockDiv(_spi, old_apb/;
        s/_div = spiFrequencyToClockDiv(_speed)/_div = gfxSpiFrequencyToClockDiv(\&_spi_bus_array[_spi_num], _speed)/' "$SPI"
sed -i 's/_div = spiFrequencyToClockDiv(_speed)/_div = gfxSpiFrequencyToClockDiv(nullptr, _speed)/' "$DMA"

# every old-style call must be gone, or the compile fails the same way
if grep -nE '[^x]spiFrequencyToClockDiv\([a-z_]+\)|[^x]spiFrequencyToClockDiv\(old_apb' "$SPI" "$DMA" | grep -v 'return spiFrequencyToClockDiv(freq)'; then
  echo "GFX patch missed a call" >&2
  exit 1
fi
echo "GFX patched for esp32 core 3.3.10+"
