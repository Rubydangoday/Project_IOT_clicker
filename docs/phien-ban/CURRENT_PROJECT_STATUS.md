# V3.18 Advertising A6/LE 1M + Cloud/Web (integrated 2026-10-15)

Main radio baseline is V3.18 bridge/PHY with V3.17 firmware. See START_HERE_ADV18.md.

New web/server features from GitHub 2026-10-14: autosync Cloud, attendance, parent accounts, teacher verification and CSV/roster imports. See CAP_NHAT_WEB_2026_10.md and HUONG_DAN_TICH_HOP_V318_CLOUD.md.

This is a source-level integration. Hardware/multi-remote, live MariaDB, Cloud Internet and production deployment are not yet verified.

---

# V3.17 — advertising radio scheduling hotfix

Read START_HERE_ADV17.md. Existing ADV16 installation: update_adv17.sh + firmware/ARS_remote_v3_17. No new DB migration. Pulsed laptop TX with receive-only gaps, exclusive nRF TX/RX, aligned diagnostic timestamps. Validated in host tests and ARM compile; hardware retest required. See tests/ADV17_RESULTS.md.

## Historical V3.16 notes

# V3.16 advertising experiment (separate from working GATT V3.15)

Use `START_HERE_ADV16.md`. Entry points: firmware/ARS_remote_v3_16,
bridge/ble_adv.py, ingest/ingest_adv.py. Requires additive adv_transactions table.
Exact token/session transactions with atomic DB commit, fair result carousel,
continuous scanner request, bounded retries, Serial metrics and optional MQTT-only
load tool. Host/ARM validation passed; physical radio/Ubuntu/MariaDB integration
still needs target testing. See tests/ADV16_RESULTS.md.

V3.15 GATT remains the fallback. Do not mix its firmware with the ADV16 services.
The installer backs up runtime and DB, then applies opt-in service overrides.

## Earlier GATT release notes

# V3.15 — Connected idle + letter answers + auto question + remote Room

Start with `START_HERE_CONNECTED_IDLE.md`. Flash `firmware/ARS_remote_v3_15`.
After 30 seconds continuously eligible and inactive, blank LEDs and block the
loop task in 20 ms intervals while keeping BLE. Open current STATE or a key
wakes the display; the waking key is consumed until full release. Unknown STATE,
open questions, editing, pending ACK/retry, errors and held keys prevent idle.
Use `tests/CONNECTED_IDLE_RESULTS.md` for verification and hardware limitations.
The server is unchanged from V3.12. Older firmware remains a fallback.

## Historical V3.14 notes

### V3.14 — Letter answers + auto question + remote-selected Room

Start with `START_HERE_LETTER_ANSWERS.md`. Flash `firmware/ARS_remote_v3_14`.
Selected answers display as a steady A/b/C/d/E/F/G/H/I/J on the right digit.
Protocol answer codes remain 1..10. Server and all other behavior are unchanged.
Previous firmware folders are preserved as fallbacks.

## V3.13 behavior retained

Historical V3.13 guide: `START_HERE_AUTO_QUESTION.md`; use V3.15 firmware for current behavior.
V3.13 firmware follows current STATE and blocks answers while closed/unknown.
Pending transactions retain their original question. Manual question keys are disabled.
Server is unchanged from V3.12. Tests: `tests/AUTO_QUESTION_RESULTS.md`.

## V3.12 server (still current)

Use `START_HERE_REMOTE_ROOM.md` and `deploy/upgrade_remote_room.sh`.
Only runtime `bridge/ble_gatt.py` changes from V3.11. It supports V3.11 and V3.13 firmware.
Room is discovered from the remote; config `[gateway] room` is ignored by this
GATT bridge. Address selection and backend validation remain in effect.

Historical V3.11 build tests: `tests/GATT_RESULTS.md`.
V3.12 lifecycle tests: `tests/REMOTE_ROOM_RESULTS.md`.
