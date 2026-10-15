# V3.11 GATT validation — 2026-10-13

## Completed

| Check | Result |
|---|---|
| Python protocol/bridge/backend unit tests | **19/19 passed** |
| Real firmware application compiled/executed against host hardware mocks | Passed |
| Arduino cross-compile with actual Adafruit nRF52 core 1.7.0 | **Passed** |
| Reference build target | `adafruit:nrf52:feather52840` (API/build check, not a claim about SuperMini board selection) |
| Flash in reference build | 138,168 / 815,104 bytes (16%) |
| Static RAM in reference build | 15,752 / 237,568 bytes (6%) |
| Python syntax check and bridge CLI help | Passed |
| Install/rollback shell syntax | Passed |

Reference build used ARM GCC 9-2019q4 and CMSIS 5.7.0. Core/tool archives were
checked against the official index checksums. The DFU ZIP packaging recipe was
disabled for this local compile; normal Arduino IDE upload on the user's laptop
uses its existing nrfutil setup. No prebuilt binary for the reference board is
included, to avoid flashing a binary built for the wrong board/bootloader.

## What the tests cover

- Fragmented/coalesced BLE UART frames, bad length/magic rejection.
- GATT request tokens retained for retry and changed across new transactions.
- Old, retained, expired or mismatching ACKs cannot complete a current request.
- Exact LOGIN/ANSWER ACK/NACK, including LOGIN rejection.
- Failed DB INSERT cannot generate a success result; existing duplicate answer
  generates a result without another response INSERT.
- Probe PING/PONG does not authorize login or synthesize backend success.
- Firmware waits for HELLO + Notify, ignores attendance as a login ACK, retries
  same transaction, cancels uncertain answer on disconnect and logs in again.
- Mode labels produce distinct seven-segment patterns, numeric phase works,
  editing stays accessible offline, heartbeat expiry invalidates readiness.

## Reproduce software checks

From project root:

```bash
python3 tests/gatt_unit.py
bash tests/firmware_host/run.sh
bash -n deploy/install_gatt.sh deploy/rollback_gatt.sh
```

The host test needs g++ and uses mocked GPIO/BLE/storage. It is not a radio test.
The old `tests/ble_scan_unit.py` belongs to the historical Advertising scheduler
and is not the regression suite for this GATT implementation.

## Still requires your physical setup

- Upload using the exact SuperMini board profile/bootloader already working for V3.10.
- PING/PONG through the laptop Bluetooth controller and PCB.
- Real MQTT/MariaDB/web end-to-end test; database tests above use fakes.
- Measure first-attempt success, ACK latency and reconnect time.
- Check glyph readability, brightness and keypad behavior on the physical display.
- Check stability on the intended PCB power supply.

No measured BLE success rate or sub-200 ms end-to-end latency is claimed yet.
