# V3.14 validation — 2026-10-13

- `bash tests/firmware_host/run.sh`: passed (real firmware with host mocks).
- Existing display scenario updated: the chosen letter remains steady across
  the previous numeric phase; question display still shows numeric values.
- ARM build passed: Adafruit nRF52 core 1.7.0, reference target Feather nRF52840.
  Flash 138552/815104 bytes; RAM 15752/237568 bytes. No hardware upload performed.
- Server, physical pin mappings, radio transport, and previous V3.13 firmware
  are byte-identical to the prior release. Application changes only its banner
  and version comment; runtime changes are confined to display.cpp.
- No new physical PCB or BLE end-to-end test. Use the known working SuperMini
  profile when flashing. Previous protocol tests were not rerun for this display edit.
