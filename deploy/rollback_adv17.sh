#!/usr/bin/env bash
# Restore only the bridge file replaced by update_adv17.sh.
set -euo pipefail
[[ $EUID -eq 0 && $# -eq 1 ]] || { echo 'sudo bash deploy/rollback_adv17.sh /opt/ars-server/backups/adv17-...'; exit 1; }
backup=$(realpath -- "$1")
[[ "$backup" == /opt/ars-server/backups/adv17-* && -f "$backup/bridge-before.tar.gz" ]] || { echo 'Not an ADV17 backup'; exit 1; }
systemctl stop ars-ble
tar -xzf "$backup/bridge-before.tar.gz" -C /opt/ars-server server/bridge/ble_adv.py
if [[ $(cat "$backup/ars-ble.active") == active ]]; then systemctl start ars-ble; fi
echo 'Previous advertising bridge restored; DB/config/ingest retained.'
echo 'For the complete old radio schedule, also flash V3.16 firmware.'
echo 'To return to GATT, use the original ADV16 backup and rollback_adv16.sh, then flash V3.15.'
