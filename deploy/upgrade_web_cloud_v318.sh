#!/usr/bin/env bash
# Web + Cloud only upgrade for an installed ARS V3.18 Advertising A6/LE 1M host.
# Does not touch firmware, BLE/PHY, ingest code, service drop-ins or adapter settings.
set -Eeuo pipefail
[[ ${EUID:-1} -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
SRC=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
DST=/opt/ars-server
[[ "$SRC" != "$DST" && -f "$DST/config.ini" && -f "$DST/server/bridge/ble_adv.py" && -f "$DST/server/ingest/ingest_adv.py" ]] || {
  echo 'Requires an existing ADV V3.18 installation in /opt/ars-server; run from an extracted merged package.' >&2; exit 1;
}
for bin in mysql mysqldump rsync php systemctl python3 tar gzip; do command -v "$bin" >/dev/null || { echo "Missing: $bin" >&2; exit 1; }; done
before_ble=$(systemctl show ars-ble -p ExecStart --value)
before_ingest=$(systemctl show ars-ingest -p ExecStart --value)
[[ "$before_ble" == *'/bridge/ble_adv.py'* && "$before_ingest" == *'/ingest/ingest_adv.py'* ]] || {
  echo 'Refusing: active service commands are not the expected Advertising/ADV ingest variants.' >&2; exit 1;
}
[[ -f /etc/systemd/system/ars-ble.service.d/zzz-adv18-phy.conf ]] || {
  echo 'Refusing: ADV18 PHY drop-in missing; inspect service state manually before updating.' >&2; exit 1;
}
php -r 'if (!extension_loaded("pdo_mysql") || !extension_loaded("curl") || !extension_loaded("mbstring")) exit(1);' || {
  echo 'Missing PHP extensions (pdo_mysql, curl or mbstring).' >&2; exit 1;
}
for migration in migrate_013_adv_transactions migrate_013_no_facebook migrate_014_attendance_parent_msgs migrate_015_cloud_autosync migrate_016_parent_phone_login migrate_017_teacher_verified; do
  [[ -f "$SRC/database/$migration.sql" ]] || { echo "Missing migration: $migration" >&2; exit 1; }
done
if [[ "${1:-}" == --dry-run ]]; then
  echo 'DRY RUN: ADV service configuration checked. Will back up DB + code, update web/db/autosync, run migrations 013(ADV)+013(Facebook)+014-017, and reload Apache.'
  echo 'Will NOT change firmware/, bridge/, ingest/, PHY systemd overrides, config.ini, or existing answers.'
  exit 0
fi
[[ $# == 0 ]] || { echo 'Usage: sudo bash deploy/upgrade_web_cloud_v318.sh [--dry-run]' >&2; exit 2; }
mysql -N -e 'SELECT 1' ars >/dev/null || { echo 'Cannot connect to the existing ars database as root.' >&2; exit 1; }
BACKUP="$DST/backups/webcloud-v318-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$DST/backups" "$BACKUP"
chmod 700 "$DST/backups" "$BACKUP"
cp "$SRC/deploy/rollback_web_cloud_v318.sh" "$BACKUP/rollback_web_cloud_v318.sh"
chmod 700 "$BACKUP/rollback_web_cloud_v318.sh"
echo "Backup directory: $BACKUP"
# Save before ANY web/data changes. Root-only dump, no plaintext credentials printed.
mysqldump --single-transaction --triggers --routines --default-character-set=utf8mb4 ars | gzip -c > "$BACKUP/database-before.sql.gz"
chmod 600 "$BACKUP/database-before.sql.gz"
# máy cài theo bố cục cũ (db/, huong-dan-su-dung/) hoặc mới (database/, docs/): chỉ sao lưu thư mục đang có
BK=(); for d in web db database deploy tests huong-dan-su-dung docs; do [[ -e "$DST/$d" ]] && BK+=("$d"); done
tar -czf "$BACKUP/code-before.tar.gz" -C "$DST" "${BK[@]}"
chmod 600 "$BACKUP/code-before.tar.gz"
# Track new files: restoring the archive alone would otherwise leave stale upgraded PHP files behind.
python3 - "$SRC" "$DST" "$BACKUP/added-files.txt" <<'PY'
from pathlib import Path
import sys
src,dst,out=map(Path,sys.argv[1:])
files=[]
for root in ('web','database','tests','docs'):
    for p in (src/root).rglob('*'):
        if p.is_file():
            rel=p.relative_to(src)
            if not (dst/rel).exists(): files.append(rel.as_posix())
for n in ('deploy/ars-autosync.php','deploy/ars-autosync.service','deploy/ars-autosync.timer','deploy/ars','deploy/install_ubuntu.sh'):
    if not (dst/n).exists(): files.append(n)
out.write_text(''.join(f+'\n' for f in sorted(set(files))))
PY
chmod 600 "$BACKUP/added-files.txt"
for n in ars-autosync.service ars-autosync.timer; do
  if [[ -f "/etc/systemd/system/$n" ]]; then cp -p "/etc/systemd/system/$n" "$BACKUP/$n.previous"; else touch "$BACKUP/$n.absent"; fi
done
if systemctl is-enabled --quiet ars-autosync.timer 2>/dev/null; then touch "$BACKUP/autosync-was-enabled"; fi
if systemctl is-active --quiet ars-autosync.timer 2>/dev/null; then touch "$BACKUP/autosync-was-active"; fi
error() { rc=$?; trap - ERR; echo "Upgrade STOPPED (code $rc). Backups retained: $BACKUP" >&2;
  echo 'Do not restore the database blindly: inspect migrations and read docs/phien-ban/HUONG_DAN_TICH_HOP_V318_CLOUD.md.' >&2; exit "$rc"; }
trap error ERR
# Only update web/business additions and CLI. No blanket rsync --delete.
rsync -a "$SRC/web/" "$DST/web/"
rsync -a "$SRC/database/" "$DST/database/"
rsync -a "$SRC/tests/" "$DST/tests/"
rsync -a "$SRC/docs/" "$DST/docs/"
for n in ars ars-autosync.php ars-autosync.service ars-autosync.timer install_ubuntu.sh; do
  install -m 755 "$SRC/deploy/$n" "$DST/deploy/$n"
done
# PHP web server sees new files; retain the service's current users and other permissions.
chown -R root:root "$DST/web" "$DST/database" "$DST/deploy"
chmod -R a+rX "$DST/web" "$DST/database" "$DST/deploy"
for migration in migrate_013_adv_transactions migrate_013_no_facebook migrate_014_attendance_parent_msgs migrate_015_cloud_autosync migrate_016_parent_phone_login migrate_017_teacher_verified; do
  echo "Applying $migration..."
  mysql ars < "$DST/database/$migration.sql"
done
cp "$DST/deploy/ars-autosync.service" "$DST/deploy/ars-autosync.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ars-autosync.timer
install -m 755 "$DST/deploy/ars" /usr/local/bin/ars
systemctl reload apache2
[[ "$(systemctl show ars-ble -p ExecStart --value)" == "$before_ble" ]] || { echo 'ARS BLE ExecStart changed unexpectedly!' >&2; false; }
[[ "$(systemctl show ars-ingest -p ExecStart --value)" == "$before_ingest" ]] || { echo 'ARS ingest ExecStart changed unexpectedly!' >&2; false; }
systemctl is-active --quiet ars-autosync.timer
trap - ERR
echo 'Web + Cloud upgrade installed. No BLE or ingest processes were restarted.'
echo 'Original database + code backup:' "$BACKUP"
echo 'Verify: ars status ; ars sync log ; journalctl -u ars-ble -u ars-ingest -n 40 --no-pager'
echo 'Rollback web code only (schema remains additive): sudo bash' "$BACKUP/rollback_web_cloud_v318.sh" "$BACKUP"
