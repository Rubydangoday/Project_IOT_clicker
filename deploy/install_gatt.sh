#!/usr/bin/env bash
# Upgrade an existing Ubuntu ARS server; preserve config/database/web.
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo 'Run: sudo bash deploy/install_gatt.sh'; exit 1; fi
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=/opt/ars-server
[[ "$src" != "$target" ]] || { echo 'Run from the newly extracted project, not /opt/ars-server'; exit 1; }
[[ -f "$target/config.ini" && -f "$target/server/ingest/ingest.py" ]] || { echo 'Existing /opt/ars-server installation required'; exit 1; }
/usr/bin/python3 -c 'import bleak, paho.mqtt.client, pymysql' || {
    echo 'Install dependencies: sudo apt install python3-bleak python3-paho-mqtt python3-pymysql'; exit 1;
}
/usr/bin/python3 -m py_compile "$src/server/bridge/ble_gatt.py" "$src/server/bridge/gatt_protocol.py" "$src/server/ingest/ingest.py"
stamp=$(date +%Y%m%d-%H%M%S)
backup="$target/backups/gatt-$stamp"
mkdir -p "$backup" "$target/server/bridge" /etc/systemd/system/ars-ble.service.d
cp -a "$target/server/ingest/ingest.py" "$backup/ingest.py"
systemctl is-enabled ars-bridge > "$backup/ars-bridge-enabled" 2>/dev/null || true
systemctl is-active ars-bridge > "$backup/ars-bridge-active" 2>/dev/null || true
if [[ -f /etc/systemd/system/ars-ble.service.d/gatt.conf ]]; then
    cp -a /etc/systemd/system/ars-ble.service.d/gatt.conf "$backup/gatt.conf"
fi
for file in ble_gatt.py gatt_protocol.py; do
    if [[ -f "$target/server/bridge/$file" ]]; then cp -a "$target/server/bridge/$file" "$backup/$file"; fi
done
systemctl stop ars-ble
systemctl disable --now ars-bridge 2>/dev/null || true
systemctl stop ars-ingest
install -m 644 "$src/server/bridge/ble_gatt.py" "$target/server/bridge/ble_gatt.py"
install -m 644 "$src/server/bridge/gatt_protocol.py" "$target/server/bridge/gatt_protocol.py"
install -m 644 "$src/server/ingest/ingest.py" "$target/server/ingest/ingest.py"
cat > /etc/systemd/system/ars-ble.service.d/gatt.conf <<'CONF'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 /opt/ars-server/server/bridge/ble_gatt.py
CONF
systemctl daemon-reload
systemctl restart ars-ingest
systemctl restart ars-ble
printf 'Installed GATT. Backup: %s\n' "$backup"
printf 'Logs: journalctl -u ars-ble -u ars-ingest -f\n'
printf 'Rollback: sudo bash deploy/rollback_gatt.sh %q\n' "$backup"
