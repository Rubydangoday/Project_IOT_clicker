#!/usr/bin/env bash
# Opt-in advertising experiment; leaves GATT scripts and original ingest intact.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run: sudo bash deploy/install_adv16.sh'; exit 1; }
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=/opt/ars-server
[[ "$src" != "$target" && -f "$target/config.ini" ]] || { echo 'Run from extracted V3.16 project with existing server installed.'; exit 1; }
for svc in ars-ble ars-ingest; do
    [[ ! -e "/etc/systemd/system/$svc.service.d/zz-adv16.conf" ]] || { echo 'ADV16 already installed; rollback before reinstall.'; exit 1; }
done
systemctl show ars-ble -p ExecStart --value | grep -q '/bridge/ble_gatt.py' || { echo 'Expected existing GATT installation.'; exit 1; }
systemctl is-active --quiet ars-bridge && { echo 'Stop the optional serial bridge before installing.'; exit 1; }
/usr/bin/python3 -c 'import bleak, dbus_fast, pymysql, paho.mqtt.client'
/usr/bin/python3 -m py_compile "$src/server/bridge/ble_adv.py" "$src/server/bridge/adv_protocol.py" "$src/server/ingest/ingest_adv.py" "$src/deploy/adv_admin.py"
/usr/bin/python3 "$src/server/bridge/ble_adv.py" --config "$target/config.ini" --check
backup="$target/backups/adv16-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$backup"
tar -czf "$backup/server-before.tar.gz" -C "$target" server/bridge server/ingest server/common config.ini
for svc in ars-ble ars-ingest; do
    systemctl is-active "$svc" > "$backup/$svc.active" || true
    systemctl cat "$svc" > "$backup/$svc.effective.txt"
done
cp "$src/deploy/rollback_adv16.sh" "$backup/rollback_adv16.sh"
# Backup completes before any service/DB modification.
/usr/bin/python3 "$src/deploy/adv_admin.py" --config "$target/config.ini" --backup-dir "$backup"
restore_error() {
    code=$?;trap - ERR
    bash "$backup/rollback_adv16.sh" "$backup" || true
    echo "Install failed; rollback attempted. Backup: $backup" >&2
    exit "$code"
}
trap restore_error ERR
systemctl stop ars-ble ars-ingest
install -d "$target/database"
install -m 644 "$src/server/bridge/ble_adv.py" "$src/server/bridge/adv_protocol.py" "$target/server/bridge/"
install -m 644 "$src/server/ingest/ingest_adv.py" "$target/server/ingest/"
# Pin the base business rules used by the subclass; backup/rollback preserves runtime original.
install -m 644 "$src/server/ingest/ingest.py" "$target/server/ingest/ingest.py"
install -m 644 "$src/database/migrate_013_adv_transactions.sql" "$target/database/"
/usr/bin/python3 "$target/server/ingest/ingest_adv.py" --config "$target/config.ini" --init-db
for svc in ars-ble ars-ingest; do install -d "/etc/systemd/system/$svc.service.d"; done
cat > /etc/systemd/system/ars-ble.service.d/zz-adv16.conf <<'CONF'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /opt/ars-server/server/bridge/ble_adv.py
CONF
cat > /etc/systemd/system/ars-ingest.service.d/zz-adv16.conf <<'CONF'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /opt/ars-server/server/ingest/ingest_adv.py
CONF
systemctl daemon-reload
systemctl show ars-ble -p ExecStart --value | grep -q '/bridge/ble_adv.py'
systemctl show ars-ingest -p ExecStart --value | grep -q '/ingest/ingest_adv.py'
systemctl start ars-ingest ars-ble
sleep 3
systemctl is-active --quiet ars-ingest
systemctl is-active --quiet ars-ble
trap - ERR
echo "ADV16 installed (hardware throughput unverified). Backup: $backup"
echo "Flash firmware/ARS_remote_v3_16/ARS_remote_v3_16.ino; start a session on the teacher web."
printf 'Rollback: sudo bash %q %q\n' "$backup/rollback_adv16.sh" "$backup"
echo 'Logs: journalctl -u ars-ble -u ars-ingest -f'
