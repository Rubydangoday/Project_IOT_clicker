#!/usr/bin/env bash
# Roll back upgraded web files; DB changes are NOT rolled back automatically.
set -Eeuo pipefail
[[ ${EUID:-1} -eq 0 && $# -eq 1 ]] || { echo 'Usage: sudo bash rollback_web_cloud_v318.sh /opt/ars-server/backups/webcloud-v318-...'; exit 1; }
B=$(realpath -- "$1")
[[ "$B" == /opt/ars-server/backups/webcloud-v318-* && -f "$B/code-before.tar.gz" && -f "$B/database-before.sql.gz" && -f "$B/added-files.txt" ]] || { echo 'Invalid backup location'; exit 1; }
D=/opt/ars-server
# Delete ONLY paths proven absent before upgrade.
while IFS= read -r rel; do
  [[ "$rel" =~ ^(web|db|database|tests|huong-dan-su-dung|docs|deploy)/[A-Za-z0-9_.+/-]+$ && "$rel" != *'..'* ]] || { echo "Refusing unsafe relative path: $rel"; exit 1; }
  rm -f -- "$D/$rel"
done < "$B/added-files.txt"
tar -xzf "$B/code-before.tar.gz" -C "$D"
for n in ars-autosync.service ars-autosync.timer; do
  if [[ -f "$B/$n.previous" ]]; then cp -p "$B/$n.previous" "/etc/systemd/system/$n";
  elif [[ -f "$B/$n.absent" ]]; then rm -f "/etc/systemd/system/$n"; fi
done
systemctl daemon-reload
if [[ -f "$B/autosync-was-enabled" ]]; then systemctl enable ars-autosync.timer >/dev/null;
else systemctl disable --now ars-autosync.timer >/dev/null 2>&1 || true; fi
if [[ -f "$B/autosync-was-active" ]]; then systemctl start ars-autosync.timer; fi
[[ -f "$D/deploy/ars" ]] && install -m 755 "$D/deploy/ars" /usr/local/bin/ars
systemctl reload apache2
echo 'Web/deploy/db FILES restored. Database migrations and any new records are still present.'
echo "Old DB snapshot (manual, destructive restore only after reviewing changes): $B/database-before.sql.gz"
echo 'BLE bridge/ingest/PHY were not touched.'
