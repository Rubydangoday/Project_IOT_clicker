# V3.12 remote-selected Room — validation 2026-10-13

29 Python tests passed (19 baseline + 10 room lifecycle tests).
The new tests execute the real bridge with fake BLE and MQTT transports:

- Boot with Room 04 while the previous configuration had Room 01.
- Switch 04 → 01 → 04 without disconnecting fake BLE; mark old room offline.
- Each MQTT client subscribes to the selected room and has that room's Last Will.
- Old-client message/disconnect callbacks cannot affect a replacement client.
- Wrong-room topic AND wrong-room STATE payload are rejected.
- An old queued/dequeued downlink is rejected by generation at actual write time.
- Clear previous snapshots and transaction tokens, even when returning to a room.
- Handle Room changing again while MQTT subscription is in progress.
- NO_SESSION result is delivered without dropping BLE.
- Link loss interrupts HELLO wait immediately; invalid Room is rejected.

Unchanged V3.11 firmware also passed the host C++ harness with new assertions:
HELLO Room 0 discovers saved identity without authorizing LOGIN; the bridge can
then send the reported Room and reauthorize LOGIN without physical disconnect.
The firmware itself is byte-identical to the previously compiled V3.11 source.
No new firmware binary/flash is necessary.

Run from project root:

```bash
python3 tests/gatt_unit.py
python3 tests/room_switch_unit.py
bash tests/firmware_host/run.sh
bash -n deploy/upgrade_remote_room.sh deploy/rollback_remote_room.sh
```

These are software tests, not measured radio/DB integration performance.
The user's prior successful BLE probe and accepted answers were on V3.11.
Physical room-switch timing, actual BlueZ/MQTT reconnection and web routing
must be verified on the user's laptop and populated PCB.
