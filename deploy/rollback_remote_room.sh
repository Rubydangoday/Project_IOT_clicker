#!/usr/bin/env bash
# Restores only the bridge changed by upgrade_remote_room.sh; preserves current DB/config.
set -euo pipefail
[[ ${EUID} -eq 0 && $# -eq 1 ]] || {
    echo 'sudo bash deploy/rollback_remote_room.sh /opt/ars-server/backups/remote-room-TIMESTAMP'; exit 1;
}
backup=$1
target=/opt/ars-server
[[ -f "$backup/ble_gatt.py" ]] || { echo 'Backup bridge not found'; exit 1; }
/usr/bin/python3 -m py_compile "$backup/ble_gatt.py"
systemctl stop ars-ble
cp -a "$backup/ble_gatt.py" "$target/server/bridge/.ble_gatt.py.restore"
mv -f "$target/server/bridge/.ble_gatt.py.restore" "$target/server/bridge/ble_gatt.py"
systemctl restart ars-ble
echo 'Previous bridge restored. V3.11 uses [gateway] room from config.ini again.'
