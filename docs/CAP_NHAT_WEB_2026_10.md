# Cập nhật phần web và máy chủ (10/2026)

Đây là bản cập nhật lớn cho **phần web và máy chủ** của ARS. Nó gồm các tính năng đã làm cho repo `ars-server` trong các buổi làm việc gần đây.

**Phần không thay đổi:** firmware, phần cứng (mạch Remote) và phần thu sóng. Cụ thể là `firmware/`, `bridge/`, `ingest/`, `common/`, `tests/firmware_host`, `tests/gatt_unit.py`, `tests/ble_scan_unit.py`, cùng các script `deploy/*gatt*.sh` và `deploy/*remote_room*.sh`. Các chữ mô tả cách thu sóng trên web và trong hướng dẫn cũng được giữ như cũ (Remote → Bluetooth của laptop), gồm các trang `session.php`, `devices.php`, `portal.php`, cài đặt "Kết nối clicker", `gateway.js` và `control.js`.

## Cách cập nhật máy chủ đang chạy

```bash
git pull
sudo bash deploy/install_ubuntu.sh      # chạy thêm migration 013–017, cài bộ hẹn giờ tự đồng bộ Cloud
ars status                              # dòng ars-autosync.timer phải là active
```

Dữ liệu cũ được giữ nguyên. Các migration đều chạy lại an toàn.

---

## 1. Điểm danh tự động và thông báo cho phụ huynh

- **Tự động điểm danh.** Học sinh **đăng nhập bằng Remote** hoặc **có câu trả lời được nhận** trong buổi là *có mặt*, còn lại là *vắng*. Ví dụ, em làm xong bài kiểm tra bằng Remote thì đã được tick có mặt.
- **Giáo viên sửa điểm danh.** Bấm nút **📋 Điểm danh** ở trang kết quả buổi hoặc trong trang lớp. Mỗi em chọn *Tự động*, *Có mặt*, *Vắng* hoặc *Vắng có phép*, có thể kèm ghi chú.
- **Điểm danh cả lớp** (`attendance.php?class=…`): bảng buổi × học sinh (✓ / ✗ / P) kèm tỉ lệ có mặt, xuất được **Excel / CSV**.
- **Thông báo phụ huynh.** Khi giáo viên bấm **Kết thúc buổi**, mỗi phụ huynh nhận một tin ở mục **🔔 Thông báo** trong trang phụ huynh: con có mặt hay vắng, kèm điểm nếu kết quả đã công bố.
  - Bài kiểm tra chưa công bố: tin ghi *"Điểm sẽ được báo khi thầy cô công bố"*. Khi công bố, chính tin đó được thêm điểm.
  - Giáo viên sửa điểm danh thì tin cũng được cập nhật.
  - Trong cả hai trường hợp, tin hiện lại là chưa đọc.
- Các trang thống kê, trang phụ huynh và trang học sinh đều tính chuyên cần theo điểm danh mới, kể cả phần giáo viên sửa tay.
- **Dữ liệu và mã:** migration `db/migrate_014_attendance_parent_msgs.sql`, gồm bảng `session_attendance`, VIEW `attendance_final` và bảng `parent_messages`. Mã nằm trong `web/attendance.php` và `web/lib/attendance.php`.

## 2. Nhập danh sách học sinh từ nhiều loại file

- Nút **Nhập danh sách (Excel, CSV, Word, TXT)** trong trang lớp nhận các file sau:
  - `.xlsx` và `.csv`;
  - `.docx`: một bảng, hoặc mỗi dòng một học sinh;
  - `.txt`: ví dụ `1. 23134001 Nguyễn Văn An 0912345678`.
- **Nhận cột theo tiêu đề**, có dấu hay không dấu đều được: STT, MSSV / Mã HS, Họ tên, **SĐT phụ huynh**.
  - File tách hai cột *Họ đệm* và *Tên* thì được tự ghép lại.
  - Cột *Họ tên phụ huynh* được bỏ qua.
  - File không có cột STT thì số ghế được đánh 1, 2, 3… theo thứ tự trong file.
- Luôn **xem trước** rồi mới xác nhận. Nhập lại file không có cột SĐT thì SĐT đã có được giữ nguyên.
- File mẫu ("Tải file mẫu") đã có thêm cột *SDT phu huynh*.
- **Mã:** `web/lib/roster.php`.

## 3. Tài khoản phụ huynh bằng số điện thoại

Cách này giống cổng phụ huynh mà nhiều trường đang dùng.

- Danh sách học sinh có thêm cột **SĐT phụ huynh**. Nhập bằng file (mục 2), hoặc bấm *Sửa* từng em.
- Trong **Thêm → Phụ huynh** (hoặc nút **📱 Tài khoản phụ huynh** trong trang lớp), bấm **⬇ Cấp tài khoản & tải file mật khẩu** (Excel / CSV).
  - File gồm: STT, họ tên học sinh, MSSV, lớp, **SĐT phụ huynh (tên đăng nhập)**, **mật khẩu lần đầu** (8 ký tự, tự tạo), trang đăng nhập, ghi chú.
  - **Anh chị em cùng SĐT** dùng chung một tài khoản và cùng mật khẩu.
  - Bấm lại lần sau chỉ cấp mật khẩu cho học sinh mới. Có ô tick để cấp lại cho những phụ huynh chưa đăng nhập.
  - Mỗi em có nút **cấp lại MK** (khi phụ huynh quên mật khẩu). Đổi SĐT thì tài khoản theo số cũ bị bỏ liên kết.
- **Phụ huynh đăng nhập bằng SĐT**: gõ `0912…`, `+84 912…` hay có dấu cách đều được.
  - **Lần đầu bắt buộc đổi mật khẩu**: tối thiểu 8 ký tự, có cả chữ và số. Chưa đổi thì không xem được trang nào.
  - Sau này đổi mật khẩu ở tab Tài khoản.
- Mật khẩu chỉ lưu dạng mã hoá: mật khẩu lần đầu chỉ có trong file tải về.
- Cách mời phụ huynh bằng **mã mời** cũ vẫn dùng song song.
- **Dữ liệu và mã:** migration `db/migrate_016_parent_phone_login.sql`. Mã nằm trong `web/lib/parent_accounts.php` và `web/parent/password.php`.

## 4. Tự động đồng bộ lên Cloud

- Dịch vụ `ars-autosync.timer` chạy 2 phút sau khi máy chủ bật, sau đó mỗi 3 phút một lần. Nó đẩy lên Cloud các buổi vừa kết thúc, điểm vừa công bố và điểm danh vừa sửa. Giáo viên quên bấm **Sync to Cloud** cũng không sao.
- **Khi mất mạng**, nó tự thử lại với khoảng cách tăng dần (3 → 6 → … → 30 phút). Nhật ký chỉ ghi lỗi đầu tiên.
- Trang **☁️ Cloud** hiện *🔄 Tự động: BẬT*. Mỗi giáo viên có thể tắt cho riêng tài khoản của mình.
- Lệnh `ars sync` gửi ngay, `ars sync log` xem nhật ký.
- Mỗi giáo viên chỉ cần nhập **địa chỉ Cloud + mã đồng bộ một lần**.
- **Dữ liệu và mã:** migration `db/migrate_015_cloud_autosync.sql`. Mã nằm trong `deploy/ars-autosync.php`, `.service` và `.timer`.
- SĐT phụ huynh và điểm danh sửa tay cũng được đồng bộ lên Cloud.

## 5. Máy chủ Cloud 24/24 (`--cloud`)

- Lệnh `sudo bash deploy/install_ubuntu.sh --cloud` cài máy chủ Cloud **không có Bluetooth/Remote**, dành cho học sinh và phụ huynh dùng ở nhà. Máy chủ này dùng link HTTPS qua Tailscale Funnel.
- Xem hướng dẫn chi tiết trong `HUONG_DAN_CLOUD.md` (ví dụ dùng Oracle Cloud Always Free).

## 6. Giáo viên đăng ký trước, nhập mã mời sau

- Ở chế độ "Cần mã mời", ô mã mời khi đăng ký **không còn bắt buộc**. Đăng ký xong là vào thẳng trang Tổng quan; mã khôi phục mật khẩu hiện ở đó một lần.
- **Có mã đúng:** tài khoản dùng đầy đủ ngay.
- **Để trống mã:** tài khoản ở trạng thái **chưa xác nhận**.
  - Vẫn dạy, soạn câu hỏi, quản lý lớp bình thường.
  - Trợ lý AI chạy chế độ Cơ bản (ngoại tuyến, không tốn API key), và chưa tải tệp lên được.
  - Học sinh chỉ học lớp của giáo viên này cũng dùng AI chế độ Cơ bản.
- Mọi trang giáo viên có **thanh nhắc nhập mã** (`web/verify.php`). Quản trị viên có nút **Duyệt** trong trang Giáo viên.
- Nhập sai mã vẫn báo lỗi và có chống dò mã.
- **Dữ liệu:** migration `db/migrate_017_teacher_verified.sql` thêm cột `teachers.verified`. Tài khoản cũ vẫn được xác nhận như trước.

## 7. Các thay đổi khác

- **Xuất điểm CSV** (BOM UTF-8, dấu `;`, chống công thức Excel):
  - bảng điểm buổi học (`export.php?format=csv`);
  - báo cáo lớp (`analytics.php?format=csv`);
  - **bảng điểm bài tập về nhà** (`homework_export.php`, Excel / CSV).
- **Bỏ đăng nhập Facebook**, chỉ giữ Google (`db/migrate_013_no_facebook.sql`).
- Lệnh `ars status` không in thừa `?` sau các dịch vụ `inactive`.
- Thêm bản dịch tiếng Anh cho mọi chữ mới.

## 8. Hướng dẫn sử dụng đã cập nhật

- `huong-dan-su-dung/giao-vien.md`: đăng ký không cần mã mời (nhập sau), nhập danh sách nhiều định dạng, điểm danh (4.2), **tài khoản phụ huynh bằng SĐT (9.1)**, tự đồng bộ Cloud, xuất điểm CSV.
- `huong-dan-su-dung/phu-huynh.md`: **đăng nhập bằng SĐT và đổi mật khẩu lần đầu** (mục 0), mục 🔔 Thông báo.
- `huong-dan-su-dung/hoc-sinh.md`, `README.md`: link Internet của máy chủ (Tailscale Funnel), cập nhật theo bản mới.
- `huong-dan-su-dung/lap-trinh-vien.md`: thư viện, migration và test mới.
- `HUONG_DAN_CLOUD.md`: tài liệu mới.

## 9. Kiểm thử

Đã chạy `bash tests/run_local.sh` ngay trên repo này, sau khi cập nhật. Mọi bộ test web đều đạt, không có cảnh báo PHP.

| Bộ test | Số kiểm tra |
|---|---|
| http_smoke | 177 |
| ingest_integration | 23 |
| attendance_integration (mới) | 38 |
| parent_accounts_integration (mới) | 59 |
| teacher_verify_integration (mới) | 29 |
| extended_integration | 57 |
| v11_integration | 199 |
| oauth_integration | 127 |
| student_signup_integration | 33 |
| i18n_integration | 31 |
| tutor_integration | 57 |

**Lưu ý:** `tests/ble_scan_unit.py` báo lỗi *"ACK preempts background frames"*. Lỗi này **có sẵn từ trước** trong phần Bluetooth của repo: chạy trên bản chưa cập nhật cũng lỗi y hệt. Bản cập nhật này không sửa phần đó vì đó là phần thu sóng.
