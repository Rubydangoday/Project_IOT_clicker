# V3.15 validation — 2026-10-14

## Automated host scenarios: PASS

Command: `bash tests/firmware_host/run.sh` (g++17, -Wall -Wextra).

Both programs compile the actual V3.15 application, BLE transport, display,
status LED and keypad scanner/debouncer. The host simulates BLE, GPIO matrix,
clock, Serial and filesystem; it does not measure physical current or RF timing.

- Baseline login/answer result matching, immutable retries, auto question,
  closed/unknown STATE, option limits, room changes and letter glyphs retained.
- No idle with missing STATE, open question, invalid open question, pending
  transaction, failed login, Room/ID edit, held key or active result flash.
- Closed/absent current question enters idle only after 30 seconds of quiet.
- Repeated HELLO and duplicate closed STATE allow continued idle for >1 minute.
- Both common-anode digit enables and all segment outputs go HIGH; status LED
  becomes Hi-Z. Display stays blank across subsequent refresh calls.
- Idle loop advances the mocked delay by 20 ms; actual scheduler power behavior
  is supported by inspected core code, not measured by the host test.
- Opening a question wakes without new login/sequence; selecting/submitting a
  subsequent answer still works. Closing during a pending answer preserves ACK/retry.
- First raw press and later debounced event are both consumed on key wake;
  held key, release, bounce, multiple keys and simultaneous OPEN + OK tested.
- Physical disconnect and heartbeat expiry wake and clear prior state;
  reconnect needs successful login and a new STATE before idle.
- Inactivity timer remains correct across uint32 millis wrap.

## ARM compile: PASS

Adafruit nRF52 core 1.7.0, reference target `adafruit:nrf52:feather52840`.
Flash **139608 / 815104 bytes**; static RAM **15768 / 237568 bytes**.
Arduino CLI 1.2.2; `recipe.objcopy.zip.pattern=` skips the unavailable DFU zip
packager only. ARM compile/link and ELF/HEX generation completed successfully.
This reference build is not a recommendation to change the working SuperMini
board profile. No binary is distributed; build/upload using the PCB's working profile.

The installed core's `delay.c` uses vTaskDelay; tickless idle is enabled, and
`port_cmsis_systick.c` uses sd_app_evt_wait when SoftDevice is active. This allows
System ON idle between work; periodic BLE, USB and other tasks may still wake CPU.

## Scope and remaining hardware validation

Server, config templates, protocol implementation and board pin mappings remain
unchanged from V3.14. Older firmware folders are preserved byte-for-byte.
Server suites were not rerun for this firmware-only change. Existing V3.14
results remain historical evidence, not a new end-to-end test of V3.15.

Not tested on the user's PCB: physical LED blanking, BLE stability while idle,
keypress latency, current consumption and battery life. Run the checklist in
`START_HERE_CONNECTED_IDLE.md` and measure current before claiming savings.
