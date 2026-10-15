#!/usr/bin/env bash
# Restore GATT code/services; retain new answers and transaction ledger.
set -euo pipefail
[[ $EUID -eq 0 && $# -eq 1 ]] || { echo 'sudo bash deploy/rollback_adv16.sh /opt/ars-server/backups/adv16-...'; exit 1; }
backup=$(realpath -- "$1")
[[ "$backup" == /opt/ars-server/backups/adv16-* && -f "$backup/server-before.tar.gz" ]] || { echo 'Not an ADV16 backup'; exit 1; }
systemctl stop ars-ble ars-ingest
for svc in ars-ble ars-ingest; do
    rm -f "/etc/systemd/system/$svc.service.d/zz-adv16.conf"
done
# Only restore the base ingest file that this installer replaced. Preserve any
# subsequent config edits and new DB answers; do not restore the SQL dump here.
tar -xzf "$backup/server-before.tar.gz" -C /opt/ars-server server/ingest/ingest.py
systemctl daemon-reload
for svc in ars-ingest ars-ble; do
    if [[ $(cat "$backup/$svc.active") == active ]]; then systemctl start "$svc"; fi
done
echo 'Original services restored. Flash V3.15 GATT firmware. Database/ledger retained.'
