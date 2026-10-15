> **V3.13:** phần server dưới đây vẫn áp dụng; tính năng tự theo câu cần nạp firmware V3.13 theo `START_HERE_AUTO_QUESTION.md`.

# V3.12 — Room lấy từ remote, giữ firmware V3.11

Bản này nâng cấp server V3.11 đang chạy BLE GATT ổn. **Không nạp lại nRF.**
Chỉ `bridge/ble_gatt.py` được thay trên laptop. Ingest, database, web, GPIO và
firmware giữ nguyên. `remote_address` trong config vẫn chọn đúng thiết bị;
`[gateway] room` không còn quyết định Room trong đường GATT V3.12.

## Cài trên máy hiện tại

Giải nén `ARS_V3_12_REMOTE_ROOM.zip` vào một thư mục mới. Mở Terminal tại
`ARS_V3_12_REMOTE_ROOM/project` trong gói giải nén, rồi chạy:

```bash
sudo bash deploy/upgrade_remote_room.sh
journalctl -u ars-ble -u ars-ingest -f
```

Không cần chạy lại `install_gatt.sh` nếu V3.11 đã hoạt động.

Script sẽ:

1. Kiểm tra server đang dùng `ble_gatt.py`.
2. Sao lưu các thư mục bridge, ingest, common và **config.ini thật trên laptop**
   vào `/opt/ars-server/backups/remote-room-TIMESTAMP-PID/server-files-before.tar.gz`.
3. Lưu bridge cũ riêng và cấu hình service hiệu lực.
4. Thay đúng file bridge, rồi khởi động lại `ars-ble`.
5. In đường dẫn backup và lệnh khôi phục chính xác.

Backup này chỉ ở laptop của bạn. Không xóa database, không sửa mật khẩu hoặc cấu
hình room cũ. Nó không phải bản dump MariaDB: nâng cấp không thay schema/dữ liệu.

## Đổi phòng trên remote

Ví dụ đang ở Room 01, muốn sang Room 04:

1. Bấm MODE để vào `Id`.
2. Bấm MODE lần nữa để vào `r`.
3. Nhập `04`, bấm OK.
4. Màn hình chuyển sang `Id`; nhập số ghế hợp lệ của lớp Room 04, bấm OK.
5. Chờ đăng nhập. `bt`/gạch chạy có thể hiện ngắn trong lúc đồng bộ.

Bridge thăm dò Room bằng HELLO mỗi khoảng 2 giây, nhận Room mới, đánh dấu gateway
phòng cũ offline, chuyển đăng ký MQTT sang phòng mới và đồng bộ lại. MQTT có thể
kết nối lại trong quá trình chuyển; **BLE được giữ kết nối khi việc chuyển thành công**.
Lỗi mất Bluetooth/MQTT thực sự vẫn có thể kích hoạt cơ chế kết nối lại bình thường.

Log dự kiến:

```text
ROOM SELECT remote=4 previous=1; BLE kept connected
GATT READY D4:10:20:56:14:F8 room=4 (remote-selected)
GATT RX room=4 type=1 seat=2 ...
BACKEND RESULT type=1 ... status=0
```

Không còn dùng `Room mismatch: remote=4 server=1` để ngắt BLE do khác config.
Remote khởi động sẵn Room 04 cũng được tiếp nhận ngay, dù config vẫn ghi Room 01.

## Điều kiện để LOGIN thành công

- Trên web phải có lớp với **room_id = 4**, không chỉ tên lớp chứa chữ “4”.
- Lớp đó phải có **buổi học đang chạy**.
- ID là **số ghế**, phải tồn tại trong lớp.
- MAC/ghế vẫn phải phù hợp quy tắc gán thiết bị hiện có.

Room/ID nhập từ remote **không tự tạo lớp, học sinh hoặc buổi học**.

| Kết quả | Nghĩa |
|---|---|
| `status=0` | Backend chấp nhận |
| `status=4` / `NO_SESSION` | Phòng chưa có buổi học đang chạy |
| `status=8` / `UNKNOWN_SEAT` | Số ghế chưa có trong lớp |
| `status=9` / `MAPPING_MISMATCH` | Khác gán MAC/ghế của lớp |
| `status=11` / `SEAT_TAKEN` | Ghế đã được thiết bị khác đăng nhập |
| `status=12` / `MAC_BOUND` | MAC đã đăng nhập ghế khác trong cùng buổi |

NACK hợp lệ không làm bridge ngắt BLE. Sửa thông tin trên web rồi MODE → OK để
LOGIN lại. Bản này không tự di chuyển quyền sở hữu ghế trong cùng buổi và không
đổi người sở hữu các đáp án đã lưu.

## Bài thử nhanh

1. Room 01 / ghế 02: LOGIN và gửi A; kiểm tra đúng lớp trên web.
2. Tạo/mở buổi học của lớp Room 04, có ghế 02.
3. Đổi Room 04 và ID 02 trên remote, không sửa config hoặc restart service.
4. LOGIN và gửi B: chỉ lớp Room 04 được cập nhật.
5. Đổi lại Room 01, LOGIN và gửi C; dữ liệu cũ ở Room 04 phải được giữ.
6. Thử Room chưa mở buổi: nhận NACK `NO_SESSION`, sau đó đổi lại phòng hợp lệ;
   không được kẹt trong vòng `Room mismatch`/timeout.
7. Thử restart remote khi nó đã lưu Room 04; server tự lấy Room 04.

Đáp án phải gửi vào câu đang mở. Nếu thử nhiều lần trên cùng câu, bật cho phép
đổi đáp án hoặc dùng câu khác; NACK `NO_CHANGE` là kiểm tra nghiệp vụ bình thường.

## Khôi phục

Chép **nguyên lệnh Rollback mà script cài đã in**, hoặc từ thư mục project:

```bash
sudo bash deploy/rollback_remote_room.sh /opt/ars-server/backups/remote-room-TIMESTAMP-PID
```

Bridge cũ được khôi phục, vẫn dùng firmware V3.11. Khi quay về V3.11, Room lại
phải khớp `[gateway] room` trong config. Đặt remote về Room 01 nếu config là 1.

File `ARS_V3_11_GATT_BACKUP.zip` được giao riêng là bản sao nguyên byte của mã
nguồn V3.11 trước khi sửa, không chứa config riêng/database trên laptop của bạn.

## Kiểm thử đã thực hiện

- 19 kiểm thử giao thức/backend/bridge: đạt.
- 10 kiểm thử bổ sung chuyển phòng và vòng đời MQTT: đạt.
- Host C++ kiểm tra mã firmware V3.11 với HELLO 0 và đổi Room: đạt.
- Python syntax và shell syntax: đạt.
- Chưa có phép thử V3.12 trên Bluetooth/laptop/PCB thật của bạn.

Chi tiết: `tests/REMOTE_ROOM_RESULTS.md`. Hướng dẫn cũ `START_HERE_GATT.md` chỉ
còn dùng cho các thao tác firmware, probe và giao diện chung; quy tắc Room cố
định trong đó được thay bằng tài liệu này.
