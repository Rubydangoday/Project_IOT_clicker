#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 && $# -eq 1 ]] || { echo 'sudo bash deploy/rollback_gatt.sh /opt/ars-server/backups/gatt-TIMESTAMP'; exit 1; }
backup=$1
target=/opt/ars-server
[[ -f "$backup/ingest.py" ]] || { echo 'Backup ingest.py not found'; exit 1; }
systemctl stop ars-ble ars-ingest
cp -a "$backup/ingest.py" "$target/server/ingest/ingest.py"
if [[ -f "$backup/gatt.conf" ]]; then
    cp -a "$backup/gatt.conf" /etc/systemd/system/ars-ble.service.d/gatt.conf
else
    rm -f /etc/systemd/system/ars-ble.service.d/gatt.conf
fi
for file in ble_gatt.py gatt_protocol.py; do
    if [[ -f "$backup/$file" ]]; then cp -a "$backup/$file" "$target/server/bridge/$file"; fi
done
systemctl daemon-reload
systemctl restart ars-ingest ars-ble
if [[ -f "$backup/ars-bridge-enabled" ]] && [[ $(cat "$backup/ars-bridge-enabled") == enabled ]]; then systemctl enable ars-bridge; fi
if [[ -f "$backup/ars-bridge-active" ]] && [[ $(cat "$backup/ars-bridge-active") == active ]]; then systemctl start ars-bridge; fi
echo 'Server restored. If returning to Advertising, also flash firmware/ARS_remote_v3_10.'
