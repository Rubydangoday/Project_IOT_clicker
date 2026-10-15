#!/usr/bin/env bash
# Capture 100 manually generated transactions (or 10-minute limit), plus final ACK drain.
set -euo pipefail
[[ $EUID -ne 0 ]] || { echo 'Run without sudo: bash tools/test_adv18_100.sh'; exit 1; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
port=${1:-/dev/ttyACM0}
[[ -e "$port" ]] || { echo "Missing serial port: $port"; exit 1; }
python3 -c 'import serial'
for cmd in btmon timeout journalctl systemctl tar; do command -v "$cmd" >/dev/null; done
for svc in ars-ble ars-ingest; do systemctl is-active --quiet "$svc"; done
sudo -v
sudo grep -q 'ADV18 running' /opt/ars-server/server/bridge/ble_adv.py
[[ -f /etc/systemd/system/ars-ble.service.d/zzz-adv18-phy.conf ]] || { echo 'Install ADV18 first.'; exit 1; }
out=$(mktemp -d "$HOME/ARS_ADV18_100_$(date +%Y%m%d_%H%M%S)_XXXX")
start=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
trace_pid=''
finish() {
    rc=$?;trap - EXIT INT TERM;set +e
    if [[ -n "$trace_pid" ]]; then sudo kill -TERM "$trace_pid" 2>/dev/null;wait "$trace_pid" 2>/dev/null;fi
    sudo journalctl -u ars-ble -u ars-ingest --since "$start" --utc -o short-iso-precise --no-pager > "$out/server.log"
    if [[ -f "$out/radio.btsnoop" ]]; then
        sudo chown "$(id -u):$(id -g)" "$out/radio.btsnoop"
        python3 "$here/verify_adv_trace.py" "$out/radio.btsnoop" > "$out/trace_check.json" 2> "$out/trace_error.txt"
        trace_rc=$?
        [[ $trace_rc -eq 0 ]] || { echo 'HCI verification failed; send logs.';rc=2; }
    fi
    printf 'test_exit=%s\n' "$rc" > "$out/run_status.txt"
    if tar -czf "$out.tar.gz" -C "$HOME" "$(basename "$out")"; then
        echo "GUI FILE: $out.tar.gz"
    else echo "Archive failed; keep $out";rc=1;fi
    exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
{ date -Is;systemctl show ars-ble ars-ingest -p Id -p ExecStart --no-pager;printf 'Serial=%s\n' "$port"; } > "$out/environment.txt"
sudo timeout --signal=TERM --kill-after=3s 660s btmon -i 0 -w "$out/radio.btsnoop" > "$out/btmon.txt" 2>&1 &
trace_pid=$!
sleep 1
kill -0 "$trace_pid"
sudo systemctl restart ars-ble
verified=0
for attempt in {1..10}; do
    sleep 1
    if python3 "$here/verify_adv_trace.py" "$out/radio.btsnoop" > "$out/preflight_trace.json" 2> "$out/preflight_error.txt"; then verified=1;break;fi
done
[[ "$verified" -eq 1 ]] || { echo 'HCI not verified. Do not send answers.';exit 2; }
echo 'BAT DAU: giu 1 cau mo trong 15 phut, cho phep doi dap an; doi diem danh neu can.'
echo 'Gui A/B/C/D -> OK -> cho ACK -> gui tiep. Dung khi thay NGUNG BAM.'
echo 'Cau hinh LE 1M duoc GIU sau phep do; firmware van V3.17.'
python3 "$here/adv_measure.py" --port "$port" --seconds 600 --target-answers 100 --drain-seconds 15 --output "$out/remote"
