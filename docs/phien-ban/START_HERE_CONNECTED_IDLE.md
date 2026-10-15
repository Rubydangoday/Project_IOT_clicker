# V3.15 — Nghỉ tiết kiệm năng lượng, giữ kết nối BLE

Remote tắt LED và giảm thời gian CPU chạy khi đang chờ câu hỏi. Giữ các chức năng
V3.14: tự theo câu giáo viên, đáp án hiển thị chữ A–J, Room/ID nhập trên remote,
chỉ báo thành công khi nhận kết quả xác nhận đúng giao dịch từ server.

## Cập nhật trên PCB đang dùng

1. Giải nén gói V3.15 vào thư mục mới; giữ thư mục dự án cũ để quay lại khi cần.
2. Mở Arduino IDE, chọn sketch
   `firmware/ARS_remote_v3_15/ARS_remote_v3_15.ino`.
   Giữ đầy đủ các file .h/.cpp trong cùng thư mục sketch.
3. Chọn đúng Board, core, bootloader và cổng USB đã nạp thành công V3.14 trên
   SuperMini của bạn. Không đổi sang Feather chỉ vì tên mục tiêu kiểm thử bên dưới.
4. Upload. Serial Monitor 115200 sẽ hiện:
   `ARS Remote V3.15 GATT connected idle / letter answers`.
5. Để server kết nối, đăng nhập thành công và nhận STATE từ server, rồi thử bảng
   tình huống bên dưới.

Nếu laptop đã chạy bridge V3.12 (phòng theo remote), chỉ cần nạp firmware này.
Không chạy lại installer, không thay config.ini hay sửa MariaDB cho tính năng nghỉ.
Nếu chưa cập nhật phần chuyển phòng V3.12, xem `START_HERE_REMOTE_ROOM.md` riêng.

## Khi nào remote nghỉ?

Phải có **30 giây liên tục đủ mọi điều kiện**:

- BLE và heartbeat HELLO vẫn sẵn sàng; đã có LOGIN thành công.
- Đã nhận STATE hợp lệ cho biết câu hiện tại đóng hoặc không có câu hiện tại.
  Không nhận được STATE không được coi là không có câu hỏi.
- Không bấm/giữ phím; không nhập Room/ID.
- Không chờ LOGIN/ANSWER ACK, không trong retry/backoff.
- Đã kết thúc báo lỗi và nháy LED báo kết quả.

Sau khi đóng câu hoặc kết thúc báo kết quả, khoảng đếm 30 giây mới bắt đầu.
HELLO định kỳ và STATE đóng lặp lại không kéo dài khoảng đếm.
Đây là trạng thái của **câu hiện tại trong STATE**, phù hợp chế độ tự theo câu
giáo viên; không suy diễn từ toàn bộ danh sách câu đang mở trong OPENMASK.

## Trong khi nghỉ và cách đánh thức

- Tắt cả hai digit và LED trạng thái; dừng quét LED 7 đoạn.
- Giữ BLE, Room/ID, trạng thái đăng nhập trong RAM.
- Vòng chương trình kiểm tra BLE và bàn phím, rồi `delay(20)` khi vẫn nghỉ.
  Trên Adafruit nRF52 core, lệnh này nhường CPU cho FreeRTOS; khi không còn việc
  phải xử lý, lõi có thể vào System ON idle giữa các sự kiện.
- Server mở câu: tự sáng màn hình, hiển thị câu mới, không cần đăng nhập lại.
- Bấm một phím: sáng màn hình; lần bấm đó chỉ đánh thức. Thả hết phím rồi bấm
  lại để chọn đáp án, OK hoặc MODE. Giữ phím hay phím dội không tạo thao tác mới.
- Mất BLE hoặc heartbeat: thoát nghỉ để hiển thị tình trạng kết nối/lỗi.
  Khi kết nối lại, phải LOGIN và nhận STATE mới trước khi đủ điều kiện nghỉ.

Đây là **System ON idle có kết nối**, không phải System OFF. Phần xử lý giao diện
có thêm độ trễ chờ vòng quét tối đa khoảng 20 ms trong điều kiện lập lịch bình
thường, ngoài độ trễ BLE/server và chống dội phím. Đây không phải cam kết độ trễ
đầu-cuối. Các tham số kết nối BLE và timeout giao dịch giữ nguyên.

Log thêm:

```text
IDLE ENTER: display off, BLE connected
IDLE WAKE: question open
IDLE WAKE: key; release before next action
IDLE WAKE: BLE not ready
```

## Thử nhanh trên mạch thật

| Thao tác | Kết quả cần thấy |
|---|---|
| Đăng nhập, đóng câu hiện tại, không chạm phím | Sau khoảng 30 giây LED tắt; không có vòng ngắt/kết nối lại |
| Để nghỉ hơn 1 phút | BLE vẫn giữ kết nối; HELLO không làm LED sáng |
| Từ web mở câu mới khi remote đang nghỉ | Remote tự sáng, hiện đúng câu |
| Chọn B rồi OK | Hiện b khi chọn; chờ rồi báo kết quả đúng như V3.14; web nhận B |
| Đóng câu, đợi nghỉ, bấm MODE | Chỉ thức; thả rồi bấm MODE lần nữa mới vào nhập ID |
| Để một câu mở hơn 30 giây | Remote vẫn sáng để làm bài |
| Giữ phím hoặc đang nhập Room/ID hơn 30 giây | Không tự tắt màn hình |
| Tắt Bluetooth laptop khi remote nghỉ | Remote thoát nghỉ và báo mất kết nối; heartbeat có thể cần tới khoảng 8 giây để hết hạn nếu chưa có sự kiện ngắt kết nối |
| Bật lại Bluetooth, đăng nhập lại | Nhận trạng thái mới rồi hoạt động bình thường |

Theo dõi server nếu cần:

```bash
journalctl -u ars-ble -u ars-ingest -f
```

## Tiết kiệm bao nhiêu?

Chưa đo dòng trên PCB của bạn. Không có số phần trăm tiết kiệm hoặc thời lượng
pin đã xác nhận. Cần đo dòng ở cùng nguồn cấp: (1) LED sáng và BLE kết nối,
(2) chế độ nghỉ và BLE kết nối, (3) lúc gửi đáp án. Đo ở nguồn pin với USB tháo
ra để USB/debug không làm sai so sánh; đấu ampe kế nối tiếp đúng cách.

EXT_VCC vẫn bật để bảo toàn mạch hiện có. LED nguồn cố định, ổn áp, USB và các
linh kiện khác có thể vẫn tiêu thụ dòng. Bản này không thêm đo pin bằng ADC,
không thay sơ đồ chân, không thay bootloader, không dùng ngắt GPIO để đánh thức.

## Chỉnh thời gian và quay lại

Trong `.ino`, `IDLE_TIMEOUT_MS=30000` đặt thời gian chờ; `IDLE_POLL_MS=20` đặt
khoảng nghỉ vòng lặp. Không tăng khoảng quét quá lớn vì có thể bỏ sót bấm nhanh
và chậm xử lý downlink. Nạp lại firmware sau khi sửa hằng số.

Muốn quay lại: nạp `firmware/ARS_remote_v3_14/ARS_remote_v3_14.ino` đã giữ nguyên
trong gói. Không cần rollback server. Chi tiết xác minh: `tests/CONNECTED_IDLE_RESULTS.md`.
