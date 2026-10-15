# V3.18 validation

- `python3 tests/adv_unit.py`: 19 offline tests passed. Includes real application
  business rules with a SQLite test adapter, commit/rollback, replay/token matching,
  ACK queue and unchanged downlink schedule. This does not validate MariaDB engine
  integration or 50-device RF capacity.
- `python3 tests/adv18_unit.py`: 11 offline tests passed. Includes Coded TX/RX mask,
  MGMT framing and readback, ctypes bind ABI, HCI trace parsing, gateway SQL percent
  formatting regression, pending/rejected/retry counting, 100-answer capture with
  fragmented serial lines and final ACK drain, repeated service initialization
  without overwriting its original PHY backup.
- Shell syntax and Python compilation passed for modified/new scripts.
- HCI verifier replayed against the actual 22:51 LE 1M capture: PASS, all 8 scan
  parameter commands PHY 0x01, enabled duplicate filter 1. Against the 22:45 capture:
  correctly rejects PHY 0x05.
- Firmware directory is byte-for-byte unchanged from V3.17; no new flash/build
  required. Existing ARM compilation evidence belongs to V3.17.
- No live Bluetooth controller, systemd installation/rollback, or MariaDB server
  was exercised in this environment. Installer checks HCI on target and rolls back
  on ordinary installation failures. Do not remove its backup directory.

Hardware evidence supplied by user, 2026-10-14 22:51 Asia/Saigon:
34 request outcomes matched backend tokens/statuses; 33 accepted, 1 QUESTION_CLOSED;
33 accepted ACKs match server q/seq/answer. Median 597 ms, p95 1172 ms, max 3260 ms,
one retry transaction. V2 experiment restored the original PHY afterward.
RSSI was stronger than previous run, so this is not a fully controlled causal test.
