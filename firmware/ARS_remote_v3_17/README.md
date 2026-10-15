# ARS Remote V3.17 — advertising scheduling hotfix

Read [START_HERE_ADV17.md](../../docs/phien-ban/START_HERE_ADV17.md).
Open ARS_remote_v3_17.ino with all files in this folder. Preserve the working
SuperMini board/core/bootloader and physical pins. Requires advertising services
ble_adv.py + ingest_adv.py and the existing ADV16 transaction ledger.

The nRF pauses scanning for each 400 ms TX burst, then listens for STATE/ACK.
The laptop bridge must also be upgraded for explicit receive-only gaps.
ACK tokens, session binding, retries, Room/ID entry, letter answers and idle UI
remain. Radio scanning outside bursts means this is not deep radio sleep.
No authentication/encryption is configured for this lab prototype.

See tests/ADV17_RESULTS.md for test scope. Hardware timing must be measured;
one remote does not validate 50 radios. V3.15 GATT remains the known fallback.
