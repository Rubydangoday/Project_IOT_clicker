# ARS Remote V3.11 — connected BLE UART, one remote

Start with [START_HERE_GATT.md](../../docs/phien-ban/START_HERE_GATT.md).

Open `ARS_remote_v3_11.ino` with every file in this folder present. Use the same
board/bootloader that worked on the physical SuperMini with V3.10.
Do not copy an advertising-only `ars_ble.cpp` into this folder.

- Existing physical GPIO, keypad mapping, flash room/seat identity are preserved.
- NUS service; peripheral TX Notify, peripheral RX Write. All single-remote
  framed packets are at most 20 bytes, so no MTU tuning is required.
- Requested connection interval 15–30 ms; final interval is central-dependent.
- HELLO readiness heartbeat; exact LOGIN and ANSWER ACK/NACK from backend.
- Up to four sends with same sequence within a connection; disconnect cancels
  pending answer with an unknown outcome, and requires fresh LOGIN on reconnect.
- UI labels: r / Id / n / An / bt / LG / Er, plus moving dashes while waiting.
- Battery value is 0/unknown until actual ADC measurement is implemented.
- Seven-segment refresh is polled without intentional BLE burst delays.
- No pairing/encryption policy is configured in this demo; deployment security is
  a separate task. Only one central can connect; close phone BLE applications.
