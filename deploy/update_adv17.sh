#!/usr/bin/env bash
# Upgrade an existing ADV16 bridge only. No DB/config/unit modification.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run: sudo bash deploy/update_adv17.sh'; exit 1; }
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=/opt/ars-server
[[ "$src" != "$target" && -f "$target/server/bridge/ble_adv.py" ]] || { echo 'Run from the extracted V3.17 project; ADV16 must already be installed.'; exit 1; }
systemctl show ars-ble -p ExecStart --value | grep -q '/bridge/ble_adv.py' || { echo 'Expected an existing advertising service, not GATT.'; exit 1; }
systemctl show ars-ingest -p ExecStart --value | grep -q '/ingest/ingest_adv.py' || { echo 'Expected ADV16 ingest.'; exit 1; }
/usr/bin/python3 -m py_compile "$src/server/bridge/ble_adv.py"
/usr/bin/python3 "$src/server/bridge/ble_adv.py" --help >/dev/null
backup="$target/backups/adv17-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$backup"
tar -czf "$backup/bridge-before.tar.gz" -C "$target" server/bridge/ble_adv.py
systemctl is-active ars-ble > "$backup/ars-ble.active" || true
systemctl cat ars-ble > "$backup/ars-ble.effective.txt"
cp "$src/deploy/rollback_adv17.sh" "$backup/rollback_adv17.sh"
restore_error() {
    code=$?;trap - ERR
    bash "$backup/rollback_adv17.sh" "$backup" || true
    echo "Upgrade failed; rollback attempted. Backup: $backup" >&2
    exit "$code"
}
trap restore_error ERR
systemctl stop ars-ble
install -m 644 "$src/server/bridge/ble_adv.py" "$target/server/bridge/ble_adv.py"
systemctl start ars-ble
sleep 3
systemctl is-active --quiet ars-ble
trap - ERR
echo "ADV17 bridge installed. Backup: $backup"
echo 'Flash firmware/ARS_remote_v3_17/ARS_remote_v3_17.ino using your working board profile.'
echo 'Confirm ADV17 running in: journalctl -u ars-ble -n 25 --no-pager'
printf 'Bridge rollback: sudo bash %q %q\n' "$backup/rollback_adv17.sh" "$backup"
