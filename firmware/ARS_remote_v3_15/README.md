# ARS Remote V3.15 — connected idle, one remote

Read [START_HERE_CONNECTED_IDLE.md](../../docs/phien-ban/START_HERE_CONNECTED_IDLE.md).
Open `ARS_remote_v3_15.ino` with every .cpp/.h file in this folder. Use the same
board, core and bootloader that successfully ran the physical SuperMini before.

- BLE NUS TX Notify uplink / RX Write downlink, exact LOGIN/ANSWER results.
- Follow the teacher's current question; steady A/b/C/d/E/F/G/H/I/J selection.
- Room/ID entry, flash identity and physical pin mapping retained.
- 30 seconds of continuously eligible inactivity enters connected idle.
- Explicit closed/absent STATE required; no idle while a question is open,
  STATE unknown, editing, a key held, pending transaction/retry or feedback active.
- Blank both digits and status LED; stop display multiplexing; `delay(20)` in
  idle allows FreeRTOS to schedule System ON idle between work and BLE events.
- Key wake consumes the whole first press until release; opening a question
  wakes automatically. HELLO/duplicate closed STATE do not reset inactivity.
- Connection loss or heartbeat timeout wakes and invalidates prior STATE.
- No System OFF, GPIO wake interrupt, battery ADC or connection interval change.
- EXT_VCC remains HIGH; battery value remains 0/unknown.

Compile/host evidence: [CONNECTED_IDLE_RESULTS.md](../../tests/CONNECTED_IDLE_RESULTS.md).
Physical power savings and RF behavior still require testing on the PCB.
