# ARS V3.18 + Web/Cloud — merge report (2026-10-15)

## Inputs

- Local baseline: `ARS_V3_18_LE1M_SERVER(1).zip` (advertising/PHY V3.18, remote V3.17).
- GitHub package: `ars-nrf52840-ble-main.zip` (commit `89f5958308d49f7396c89fdc2435cde675ba28af`, 14 Oct 2026).

## Merge policy

- **Do not replace** radio firmware, `bridge/`, `ingest/`, `common/`, ADV performance scripts, firmware host tests, original ADV migrations, GATT fallback code, and V3.18 configuration/rollback tools.
- Merge GitHub's `web/`, latest `huong-dan-su-dung/`, new tests and test runner, migrations 013 (Facebook) to 017, Cloud autosync and service installer logic. Keep both independent migration 013 scripts.
- Fix installer to preserve `/opt/ars-server/backups/` and its secrets during rsync/chmod; startup ADV18 PHY state may be referenced there.
- Add a targeted upgrade script and code-only rollback for running V3.18 laptops, without restarting/overwriting BLE or ingest.
- Keep `bai-giang/` source materials in the FULL distribution only (they are not needed for the app at runtime).

## Offline validation (performed in artifact-build environment)

- Python source compile: **40/40**.
- PHP syntax check: **105/105**.
- App JavaScript Node syntax check: **13/13**.
- ADV A6 backend unit tests: **19/19 pass**.
- ADV18 PHY/HCI unit tests: **11/11 pass**.
- Advertising remote firmware host test: **pass**.
- GATT firmware + power host tests: **pass**.
- Bash syntax tests (`install_ubuntu.sh`, `ars`, new update + rollback, run_local): **pass**.
- Byte comparison of preserved V3.18 BLE/ingest/firmware/ADV source files: **96/96 identical** to baseline.

**Not executed:** web end-to-end/integration tests from `tests/run_local.sh`, Cloud HTTP sync with real VPS, real MariaDB migrations against production, live nRF/HCI BLE scan and 50-remote throughput tests. This artifact-build environment lacked MariaDB server and PHP `pdo_mysql`/`curl`/`mbstring` extensions. Do not treat syntax/unit passes as production approval.

## Deploy

See [`HUONG_DAN_TICH_HOP_V318_CLOUD.md`](HUONG_DAN_TICH_HOP_V318_CLOUD.md). On an **already working V3.18 laptop**, use `sudo bash deploy/upgrade_web_cloud_v318.sh` from an **extracted merged source directory**; it records DB + code backups before changes. For a **new Cloud VPS**, `sudo bash deploy/install_ubuntu.sh --cloud` and configure the sync token according to `HUONG_DAN_CLOUD.md`.

The legacy `install_ubuntu.sh` on fresh laptops retains the GATT default; switching to A6/LE 1M is opt-in via `install_gatt.sh` -> `install_adv16.sh` -> `update_adv17.sh` -> `update_adv18.sh`. No user GitHub repository or production server was modified during this merge.

## Known effects/limits

- `db/migrate_013_no_facebook.sql` removes stored Facebook OAuth links and keys. Account-password/Google alternatives remain; restore DB snapshot only with care.
- Cloud sync is one-way: laptop -> Cloud. Pending classroom events are held until connectivity returns. Cloud requires separate server and network access.
- Parent notifications are in the parent web portal, not SMS/Zalo push.
- Uploaded local remote may be using the user's later `setInterval(80,80)` and first-attempt jitter `0–50 ms`; that radio configuration is **not** in the baseline firmware V3.17 source here. No firmware flash is required or advised for this server-only update.
- New installer preserves backups but does not automatically activate V3.18 ADV on clean laptops; old service drop-ins are expected for upgraded, working hosts.
