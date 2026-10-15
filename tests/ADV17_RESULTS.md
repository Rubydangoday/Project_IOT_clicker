# ADV17 validation — 2026-10-14

- 19 Python tests passed: existing protocol/backend transaction tests plus
  receive-only gaps, idle STATE cadence, and fair 50-result queue at 400 ms slots.
  The production ingest source is unchanged. Database tests use SQLite with a
  test-only SQL syntax adapter; they do not validate MariaDB-specific behavior.
- Real firmware sources with host mocks passed: TX and scanner never overlap
  in application state; bounded burst restores scanner; queued callback does not
  resume RX during TX; failed advertising start/scan stop/scan restart recover;
  exact token ACK, wrong room/stale ACK rejection, retry identity, fresh token,
  session switch, expired STATE recovery, bounded timeout, entropy failure,
  idle and wake behavior retained.
- ARM compile/link passed with Adafruit nRF52 core 1.7.0, reference FQBN
  adafruit:nrf52:feather52840: 135540 bytes flash / 15500 bytes static RAM.
  This checks APIs and linkage, not the user's board/bootloader compatibility.
  Use their known-working SuperMini profile. DFU packaging skipped because
  nrfutil is unavailable; no compiled firmware binary is distributed.
- Upgrade/rollback shell syntax and Python syntax checked. Deployment has not
  been executed against the user's Ubuntu system. Upgrade changes only the
  advertising bridge; rollback restores that file. No DB migration is added.
- Measurement parser accepts timestamped V3.17 lines and old V3.16 logs.
  GATT V3.15, ADV16 firmware, protocol, ingest and DB source preserved.

No physical radio, actual timing improvement, power consumption, 50-device RF
capacity or actual Ubuntu installation is claimed. The supplied user capture
establishes the V3.16 delay (4 accepted answers, median 7917.5 ms), not V3.17 results.
BlueZ registration and Serial host timestamps are diagnostic software timestamps,
not exact over-the-air transmit timestamps.
