#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 && $# -eq 1 ]] || { echo 'sudo bash deploy/rollback_adv18.sh /opt/ars-server/backups/adv18-...'; exit 1; }
backup=$(realpath -- "$1")
[[ "$backup" == /opt/ars-server/backups/adv18-* && -f "$backup/files-before.tar.gz" && -f "$backup/phy_before.json" ]] || { echo 'Not an ADV18 backup'; exit 1; }
systemctl stop ars-ble ars-ingest
rm -f /etc/systemd/system/ars-ble.service.d/zzz-adv18-phy.conf
# Restore PHY with the backed-up helper before replacing runtime files.
/usr/bin/python3 "$backup/adv_phy.py" restore --index 0 --state "$backup/phy_before.json"
tar -xzf "$backup/files-before.tar.gz" -C /opt/ars-server
if [[ -f "$backup/absent.txt" ]]; then
    while IFS= read -r f; do
        case "$f" in
            server/bridge/adv_phy.py|tools/verify_adv_trace.py) rm -f "/opt/ars-server/$f" ;;
            *) echo "Unexpected absent-file entry: $f"; exit 1 ;;
        esac
    done < "$backup/absent.txt"
fi
systemctl daemon-reload
systemctl start ars-ingest ars-ble
echo 'Restored previous bridge, ingest and PHY; database/config/firmware retained.'
