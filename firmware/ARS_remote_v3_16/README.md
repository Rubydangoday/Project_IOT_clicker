# ARS Remote V3.16 — experimental advertising

Start at [START_HERE_ADV16.md](../../docs/phien-ban/START_HERE_ADV16.md).
Open `ARS_remote_v3_16.ino` with all files in this directory; preserve the known
working SuperMini board/core/bootloader and physical pin mapping.

This firmware requires **ble_adv.py + ingest_adv.py + the additive DB migration**.
It is not compatible with a running GATT bridge or the old A5 advertising bridge.

A6 Manufacturer Data protocol: 21-byte uplink, session-bound random 64-bit token,
exact LOGIN/ANSWER results. Retry keeps token and payload; fresh OK creates a new
transaction even if the 8-bit seq wraps. Success LED follows the committed backend
result. No authentication/encryption is configured for this lab prototype.

The UI retains Room/ID entry, question following, letter answers, and display/CPU
idle after 30 seconds of eligible inactivity. Radio scanning remains enabled;
there is no measured battery-life improvement or 50-radio capacity claim.

The V3.15 GATT folder remains unchanged as fallback. Full validation limitations:
[ADV16_RESULTS.md](../../tests/ADV16_RESULTS.md).
