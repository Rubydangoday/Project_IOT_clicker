#!/usr/bin/env bash
# Update an installed ADV17/18 server; firmware and database schema are unchanged.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run: sudo bash deploy/update_adv18.sh'; exit 1; }
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target=/opt/ars-server
dropin=/etc/systemd/system/ars-ble.service.d/zzz-adv18-phy.conf
[[ "$src" != "$target" && -f "$target/server/bridge/ble_adv.py" ]] || { echo 'Run from extracted project with ADV17 installed.'; exit 1; }
[[ ! -e "$dropin" ]] || { echo 'ADV18 already installed. Use its backup rollback before reinstalling.'; exit 1; }
for svc in ars-ble ars-ingest; do systemctl is-active --quiet "$svc"; done
systemctl show ars-ble -p ExecStart --value | grep -q '/bridge/ble_adv.py'
systemctl show ars-ingest -p ExecStart --value | grep -q '/ingest/ingest_adv.py'
for cmd in btmon timeout tar; do command -v "$cmd" >/dev/null; done
# This release targets the tested hci0 setup. Do not silently configure a different adapter.
/usr/bin/python3 - "$target" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'server'/'common'))
import arscfg
cp=arscfg.load(str(Path(sys.argv[1])/'config.ini'))
assert cp.get('ble','adapter',fallback='hci0')=='hci0', 'This installer requires adapter hci0'
PY
exec_line=$(systemctl show ars-ble -p ExecStart --value)
[[ "$exec_line" != *--adapter* && "$exec_line" != *--config* ]] || { echo 'Custom adapter/config command line: inspect before installing.'; exit 1; }
/usr/bin/python3 -m py_compile "$src/server/bridge/adv_phy.py" "$src/server/bridge/ble_adv.py" "$src/server/ingest/ingest_adv.py" "$src/tools/verify_adv_trace.py"
/usr/bin/python3 "$src/server/bridge/ble_adv.py" --help >/dev/null
backup="$target/backups/adv18-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$backup"
files=(server/bridge/ble_adv.py server/ingest/ingest_adv.py server/bridge/adv_phy.py tools/verify_adv_trace.py)
existing=()
for f in "${files[@]}"; do
    if [[ -e "$target/$f" ]]; then existing+=("$f"); else echo "$f" >> "$backup/absent.txt"; fi
done
tar -czf "$backup/files-before.tar.gz" -C "$target" "${existing[@]}"
cp "$src/server/bridge/adv_phy.py" "$backup/adv_phy.py"
cp "$src/deploy/rollback_adv18.sh" "$backup/rollback_adv18.sh"
systemctl cat ars-ble > "$backup/ars-ble.effective.txt"
/usr/bin/python3 "$backup/adv_phy.py" save --state "$backup/phy_before.json" > "$backup/phy_before.log"
trace_pid=''
stop_trace() {
    if [[ -n "$trace_pid" ]]; then kill -TERM "$trace_pid" 2>/dev/null || true; wait "$trace_pid" 2>/dev/null || true; trace_pid=''; fi
}
failed() {
    code=$?;trap - ERR INT TERM
    set +e
    stop_trace
    bash "$backup/rollback_adv18.sh" "$backup"
    echo "Upgrade failed (code $code); rollback attempted. Logs: $backup" >&2
    exit 1
}
trap failed ERR
trap 'false' INT TERM
systemctl stop ars-ble ars-ingest
install -d "$target/tools"
install -m 644 "$src/server/bridge/ble_adv.py" "$src/server/bridge/adv_phy.py" "$target/server/bridge/"
install -m 644 "$src/server/ingest/ingest_adv.py" "$target/server/ingest/"
install -m 644 "$src/tools/verify_adv_trace.py" "$target/tools/"
install -d "$(dirname "$dropin")"
cat > "$dropin" <<CONF
[Service]
# Root only for Bluetooth MGMT; the bridge continues running as its existing user.
ExecStartPre=+/usr/bin/python3 /opt/ars-server/server/bridge/adv_phy.py ensure --index 0 --state $backup/phy_before.json
CONF
systemctl daemon-reload
timeout --signal=TERM --kill-after=3s 25s btmon -i 0 -w "$backup/startup.btsnoop" > "$backup/btmon.txt" 2>&1 &
trace_pid=$!
sleep 1
kill -0 "$trace_pid"
systemctl start ars-ingest ars-ble
verified=0
for attempt in {1..10}; do
    sleep 1
    if /usr/bin/python3 "$target/tools/verify_adv_trace.py" "$backup/startup.btsnoop" > "$backup/hci_check.json" 2> "$backup/hci_error.txt"; then verified=1; break; fi
done
stop_trace
[[ "$verified" -eq 1 ]]
/usr/bin/python3 "$target/tools/verify_adv_trace.py" "$backup/startup.btsnoop" > "$backup/hci_check.json"
systemctl is-active --quiet ars-ble
systemctl is-active --quiet ars-ingest
trap - ERR INT TERM
echo "ADV18 installed; HCI LE 1M + duplicate filter verified. Backup: $backup"
echo 'Keep the existing V3.17 remote firmware. No flashing required.'
printf 'Rollback: sudo bash %q %q\n' "$backup/rollback_adv18.sh" "$backup"
echo 'Next: bash tools/test_adv18_100.sh'
