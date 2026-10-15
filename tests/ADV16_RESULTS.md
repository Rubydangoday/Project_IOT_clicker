# ADV16 experimental validation — 2026-10-14

## Completed

- 17 Python tests in `tests/adv_unit.py`: passed. Codec size/validation, fair
  50-result carousel, bounds/expiry, broker loss, stale STATE, exact result match,
  fault injection, retiring only the same device's old result, durable ledger,
  rollback before ledger update, failed commit, failed MQTT publish after commit,
  restart/retry, session isolation, token reuse rejection, independent new token
  with recycled seq, and 50 virtual devices × five copies of each answer.
- Backend tests run the real AdvIngest and base business rules with a test-only
  SQL syntax adapter and SQLite persistence. They verify actual commit/rollback
  behavior in that harness. **MariaDB engine integration has not been run here.**
- `bash tests/adv_firmware_host/run.sh`: passed. Real V3.16 application/transport,
  keypad/display/status source with host mocks: no sending before STATE, exact
  login/answer token checks, same-token retry, new-token repeated seq, stale and
  other-room ACK rejection, close during answer, session change, bounded timeout,
  entropy unavailable, idle and automatic open-question wake, scanner remains enabled.
- ARM compile/link: passed with Adafruit nRF52 core 1.7.0 and reference FQBN
  adafruit:nrf52:feather52840. Flash 134484 / 815104 bytes; static RAM
  15496 / 237568 bytes. DFU zip packaging skipped because nrfutil unavailable;
  ELF/HEX built. Use the existing working SuperMini profile to upload, not this
  reference board name blindly. No binary or hardware upload supplied.
- Python syntax and deployment shell syntax checks passed.
- Measurement parser tested with synthetic success, timeout and incomplete-log
  inputs; synthetic timing values are not presented as actual measurements.
- Existing GATT transport/firmware and original base ingest are preserved in
  the source tree. ADV16 is selected only through explicit deployment drop-ins.

## Not established

No BLE adapter is attached here; no RF packet trace, actual simultaneous scan /
advertising validation, laptop D-Bus permission test, physical keypad/LED test,
real power measurement, installer execution on Ubuntu, or 50-radio capacity test
has been performed. MariaDB migration/backup and backend behavior must be checked
on the user's test installation. The installer backs up first and requires InnoDB.

A fair queue with 50 entries does not prove 50 radios work concurrently. With
180 ms dwell and two results/page, 25 ACK pages alone take 4.5 seconds, plus STATE
slots, D-Bus overhead and retransmissions. The implementation does not claim
500 ms / 99.9% delivery at 50 devices. Test and tune with hardware before setting
such acceptance targets.

## Primary API references used

- https://github.com/bluez/bluez/blob/master/doc/org.bluez.LEAdvertisement.rst
- https://bluez.readthedocs.io/en/latest/advertising-api/
- https://bleak.readthedocs.io/en/latest/backends/linux.html
- https://docs.silabs.com/bluetooth/10.1.2/bluetooth-le-fundamentals/04-link-layer
- Installed Adafruit nRF52 core 1.7.0 BLEScanner/BLEAdvertising headers and
  SoftDevice S140 random-vector API; runtime changes validated by ARM compilation.
