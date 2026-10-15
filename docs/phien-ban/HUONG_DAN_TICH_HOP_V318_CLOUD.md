# Hợp nhất ARS V3.18 (ADV18 LE 1M) + Web / Cloud 10/2026

**Baseline radio (giữ nguyên):** firmware `firmware/ARS_remote_v3_17/`, `bridge/ble_adv.py`, `bridge/adv_protocol.py`, `bridge/adv_phy.py`, `ingest/ingest_adv.py`, `ingest/ingest.py`, cơ chế transaction/ACK/retry và các systemd drop-in `zz-adv16.conf`, `zzz-adv18-phy.conf` trên máy đang chạy.

**Nguồn web / Cloud:** `ars-nrf52840-ble` main ngày 14/10/2026, commit `89f5958308d49f7396c89fdc2435cde675ba28af`; gồm điểm danh tự động, thông báo trong cổng phụ huynh, nhập danh sách Word/Excel/CSV/TXT, phụ huynh dùng SĐT, giáo viên xác minh sau, đồng bộ Cloud 3 phút, cập nhật web và database.

> Đây là bản **merge mã nguồn**. Các kiểm thử phần mềm có thể chạy offline, nhưng chưa chứng minh hoạt động trên laptop/nRF/MariaDB/Cloud thật. Không thay đổi firmware của remote đã nạp. Nếu remote của bạn đang dùng interval=80 và jitter lần đầu 0-50 ms, bản firmware trong ZIP vẫn là firmware gốc V3.17 của baseline; hãy giữ firmware trên thiết bị đang hoạt động hoặc đối chiếu source đúng trước khi flash lại.

## A. Nâng cấp laptop đang chạy V3.18 — Khuyến nghị

Không thay toàn bộ server bằng bản từ GitHub: nó đang dùng firmware V3.14, GATT bridge, ingest cũ. **Không chạy `git pull && sudo bash deploy/install_ubuntu.sh` từ repo cũ**, vì sẽ có nguy cơ thay mã ADV và mất backup.

1. Đảm bảo máy đang chạy đúng V3.18. Sao lưu DB và code riêng nếu có thể, lên lịch bảo trì ngắn:

```bash
ars status
systemctl show ars-ble -p ExecStart --value
systemctl show ars-ingest -p ExecStart --value
systemctl cat ars-ble
```

`ExecStart` cần trỏ tới `bridge/ble_adv.py` và `ingest/ingest_adv.py`; `ars-ble` cần drop-in `zzz-adv18-phy.conf`.

2. Giải nén ZIP **bản hợp nhất** vào thư mục khác `/opt/ars-server` (ví dụ `~/ars-nrf52840-ble`); chạy từ thư mục đó:

```bash
cd ~/ars-nrf52840-ble
sudo bash deploy/upgrade_web_cloud_v318.sh --dry-run
sudo bash deploy/upgrade_web_cloud_v318.sh
```

Script nâng cấp sẽ:

- Kiểm tra hệ thống đang dùng ADV18, PHP extensions và DB.
- Lưu **DB dump** và snapshot code trước khi thay vào `/opt/ars-server/backups/webcloud-v318-*` (chỉ root có quyền đọc).
- Chép **web, db, tests, hướng dẫn, Cloud timer, CLI** và không sửa `firmware/`, `bridge/`, `ingest/`, `config.ini` hoặc systemd BLE drop-ins.
- Áp dụng riêng cả `migrate_013_adv_transactions.sql` (đã có ở ADV) và `migrate_013_no_facebook.sql` (bản web mới), tiếp `migrate_014` đến `migrate_017`.
- Bật `ars-autosync.timer`, reload Apache; **không restart Bluetooth hoặc ingest**.

**Lưu ý dữ liệu:** migration 013_no_facebook xóa liên kết OAuth Facebook và cấu hình Facebook; người dùng vẫn có thể dùng mật khẩu ARS/Google. Bản DB trước nâng cấp được lưu để khôi phục nếu thật sự cần.

3. Kiểm tra sau cập nhật:

```bash
ars status
systemctl show ars-ble -p ExecStart --value
systemctl show ars-ingest -p ExecStart --value
systemctl cat ars-ble
sudo systemctl status ars-autosync.timer --no-pager
journalctl -u ars-ble -u ars-ingest -n 50 --no-pager
ars sync log
```

Kiểm tra thủ công trên web: lớp → nhập danh sách → điểm danh → kết thúc buổi → phụ huynh xem thông báo; đăng ký giáo viên chưa có mã mời; gửi câu trả lời bằng remote rồi xác minh trong `responses`, `final_answers` / `adv_transactions` theo quy trình cũ.

## B. Cài máy Cloud mới

Máy Cloud riêng (Ubuntu) **không kết nối remote**:

```bash
cd ~/ars-nrf52840-ble
sudo bash deploy/install_ubuntu.sh --cloud
ars status
```

Làm tiếp các bước Oracle VPS, HTTPS Tailscale Funnel, phát hành sync token theo `HUONG_DAN_CLOUD.md`. Mỗi giáo viên trên laptop cấu hình địa chỉ Cloud và token một lần, bấm thử Sync. Trên laptop, timer chạy sau 2 phút rồi mỗi 3 phút; mất mạng sẽ retry có backoff. Đây là đồng bộ **một chiều** laptop → Cloud. Cloud không tự phản hồi ngược bài tập về laptop; dữ liệu lớp/học sinh trên laptop là nguồn chuẩn. Trang phụ huynh nhận **thông báo trong web**, không phải gửi SMS/Zalo tự động.

## C. Cài laptop mới từ đầu

`install_ubuntu.sh` mặc định dùng bridge BLE legacy `ble_scan.py`, **không tự bật ADV A6**, để tránh cấu hình sai adapter chưa kiểm chứng. Sau khi cài, để chuyển lên V3.18 phải đi đúng thứ tự, theo các tài liệu đi kèm:

```bash
sudo bash deploy/install_gatt.sh      # chuyển legacy bridge sang ble_gatt.py
sudo bash deploy/install_adv16.sh     # tạo bảng ADV và systemd drop-ins Advertising
sudo bash deploy/update_adv17.sh     # cải tiến lịch radio
sudo bash deploy/update_adv18.sh     # buộc adapter hci0 dùng LE 1M, phải kiểm tra HCI
```

**Các lệnh này là quy trình nhiều giai đoạn, có kiểm tra điều kiện và có thể khởi động lại dịch vụ.** Chỉ thực hiện khi adapter/hardware/firmware đáp ứng và có bản sao dữ liệu; xem `START_HERE_GATT.md`, `START_HERE_ADV16.md`, `START_HERE_ADV17.md`, `START_HERE_ADV18.md`. Không flash firmware V3.14 từ các hướng dẫn GitHub cũ. Remote ADV đã chạy ổn định cần giữ V3.17 đang nạp.

Script installer gốc được sửa để **không xóa `/opt/ars-server/backups/` bằng `rsync --delete` và không làm backup dễ đọc bởi người dùng khác**. ADV18 drop-in có thể trỏ tới file `phy_before.json` trong thư mục đó, không được xóa.

## D. Rollback

Script nâng cấp in ra thư mục backup, ví dụ `/opt/ars-server/backups/webcloud-v318-20261015-...`.

Khôi phục **file code/web/deploy** (không tự động khôi phục DB):

```bash
sudo bash /opt/ars-server/backups/webcloud-v318-.../rollback_web_cloud_v318.sh /opt/ars-server/backups/webcloud-v318-...
```

Migrations vẫn còn và thông thường là phép mở rộng schema. Việc khôi phục database từ `database-before.sql.gz` là thao tác **có thể xóa dữ liệu phát sinh sau lúc sao lưu**, phải dừng ghi, tạo backup mới, kiểm tra sự khác biệt và được người quản trị quyết định riêng. Không tự động khôi phục trên máy đang có người dùng.

Nếu script nâng cấp dừng giữa chừng, **không tiếp tục dùng web đang dở dang**: giữ nguyên thư mục backup, đọc lỗi migration/timer, kiểm tra MariaDB và code rồi mới retry hoặc rollback file.

## E. Đối chiếu thay đổi

| Phần | Kết quả |
|---|---|
| `firmware/ARS_remote_v3_17`, `bridge/ble_adv.py`, `ingest/ingest_adv.py`, `bridge/adv_phy.py` | Giữ từ V3.18 |
| `web/` | Lấy cập nhật GitHub 14/10 (gồm API/cloud, attendance, parent, teacher) |
| `db/migrate_013_adv_transactions.sql` | Giữ từ V3.18 |
| `db/migrate_013_no_facebook.sql`, `migrate_014`–`migrate_017` | Thêm từ GitHub |
| `deploy/install_ubuntu.sh`, `deploy/ars` | Hợp nhất Cloud và bảo vệ backup/ADV |
| `deploy/upgrade_web_cloud_v318.sh` / `rollback_web_cloud_v318.sh` | Tạo mới để cập nhật an toàn trên máy V3.18 |
| `tests/` | Giữ tất cả ADV tests; cập nhật và bổ sung web/Cloud tests |
| `bai-giang/`, `de-thi-test/` | Tài nguyên GitHub được giữ trong gói FULL; gói CODE không có `bai-giang/` |

Nguồn cập nhật: [repo GitHub](https://github.com/verasol23/ars-nrf52840-ble); mã nguồn của bản đã upload về cuộc trò chuyện này. Không có thay đổi tự động nào đã thực hiện lên server thật hay GitHub.
