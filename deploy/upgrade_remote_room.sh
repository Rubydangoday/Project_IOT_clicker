#!/usr/bin/env bash
# V3.11 -> V3.12: change only the running GATT bridge; back up first.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo 'Run: sudo bash deploy/upgrade_remote_room.sh'; exit 1; }
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=/opt/ars-server
[[ "$src" != "$target" ]] || { echo 'Run from the newly extracted V3.12 folder'; exit 1; }
for f in server/bridge/ble_gatt.py server/bridge/gatt_protocol.py server/ingest/ingest.py server/common/arscfg.py config.ini; do
    [[ -f "$target/$f" ]] || { echo "Missing $target/$f; install V3.11 first"; exit 1; }
done
/usr/bin/python3 -c 'import bleak, paho.mqtt.client'
# Verify the runtime service is already the GATT service, not Advertising.
exec_start=$(systemctl show ars-ble -p ExecStart --value)
[[ "$exec_start" == *"/opt/ars-server/server/bridge/ble_gatt.py"* ]] || {
    echo 'ars-ble is not running the V3.11 GATT entrypoint. Stop and check configuration.'; exit 1;
}
/usr/bin/python3 -m py_compile "$src/server/bridge/ble_gatt.py"
backup="$target/backups/remote-room-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$backup"
# Includes actual local config; stored locally, never sent elsewhere.
tar -czf "$backup/server-files-before.tar.gz" -C "$target" server/bridge server/ingest server/common config.ini
cp -a "$target/server/bridge/ble_gatt.py" "$backup/ble_gatt.py"
systemctl cat ars-ble > "$backup/ars-ble-effective.service.txt"
cp "$src/deploy/rollback_remote_room.sh" "$backup/rollback_remote_room.sh"
old_active=$(systemctl is-active ars-ble || true)
printf '%s\n' "$old_active" > "$backup/previous-service-state.txt"
restore_on_error() {
    result=$?
    trap - ERR
    cp -a "$backup/ble_gatt.py" "$target/server/bridge/ble_gatt.py"
    rm -f "$target/server/bridge/.ble_gatt.py.new"
    if [[ "$old_active" == active ]]; then systemctl restart ars-ble || true; fi
    printf 'Upgrade failed; restored old bridge. Backup: %s\n' "$backup" >&2
    exit "$result"
}
trap restore_on_error ERR
systemctl stop ars-ble
install -m 644 "$src/server/bridge/ble_gatt.py" "$target/server/bridge/.ble_gatt.py.new"
mv -f "$target/server/bridge/.ble_gatt.py.new" "$target/server/bridge/ble_gatt.py"
systemctl restart ars-ble
systemctl is-active --quiet ars-ble
trap - ERR
printf 'V3.12 installed. Room now follows the remote; no firmware upload required.\n'
printf 'Runtime backup: %s\n' "$backup"
printf 'Rollback: sudo bash %q %q\n' "$backup/rollback_remote_room.sh" "$backup"
printf 'Check logs: journalctl -u ars-ble -u ars-ingest -f\n'
