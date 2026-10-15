> **V3.14:** đọc `START_HERE_LETTER_ANSWERS.md` trước và nạp firmware V3.14.
> Đáp án hiện bằng chữ; phần hiển thị bằng số bên dưới là mô tả V3.13.

# V3.13 — Remote tự theo câu giáo viên đang mở

Nâng cấp từ V3.12: **nạp lại firmware nRF**. Server dùng nguyên bridge V3.12
chuyển phòng theo remote; không cần sửa config, database hoặc cài lại server
nếu bạn đã cài V3.12.

## 1. Nạp remote

1. Giải nén gói vào thư mục mới.
2. Trong Arduino IDE, mở toàn bộ thư mục `firmware/ARS_remote_v3_13`,
   chọn `ARS_remote_v3_13.ino`.
3. Giữ Board, core và cổng USB đã nạp thành công bản đang dùng trên SuperMini.
   Upload sketch này bằng quy trình cũ; không nạp bootloader hoặc xóa flash toàn bộ.
4. Serial Monitor 115200 phải hiện `ARS Remote V3.13 GATT auto question`.
5. Chờ Bluetooth tự nối và LOGIN. Room/ID dùng cùng file lưu như V3.11.

Nếu server vẫn là V3.11, mở Terminal trong thư mục `project` của gói mới:

```bash
sudo bash deploy/upgrade_remote_room.sh
journalctl -u ars-ble -u ars-ingest -f
```

Script này sao lưu server hiện tại trước khi cập nhật bridge chuyển phòng.
Nếu đã cài V3.12, bỏ qua bước script. Xem `START_HERE_REMOTE_ROOM.md` về Room/ID.

## 2. Cách sử dụng

Giáo viên mở câu trên web → remote tự hiển thị số thứ tự câu → học sinh chọn
A–J → bấm OK → chờ kết quả backend. Chỉ các đáp án có trong câu mới được chọn.
Ví dụ câu có A–D thì E–J bị chặn ngay trên remote.

| Hiển thị | Ý nghĩa |
|---|---|
| `n` ↔ `05` | Câu 05 đang mở, có thể chọn đáp án |
| `An` ↔ `03` | Đã chọn C, chưa gửi; A–J tương ứng 01–10 |
| `CL` | Câu hiện tại đã đóng; không chọn/gửi đáp án |
| `--` đứng yên | Chưa có trạng thái câu hợp lệ; chờ giáo viên mở câu hoặc server đồng bộ |
| Hai gạch chạy luân phiên | Đang chờ kết quả LOGIN/ANSWER |
| `r` ↔ số | Nhập phòng |
| `Id` ↔ số | Nhập ID/số ghế |
| `bt` nhấp nháy | Chưa kết nối ứng dụng hoặc đang nối lại |
| `LG` | Chưa đăng nhập thành công; kiểm tra phòng, buổi học và ghế |
| `Er` + đỏ | Lựa chọn không hợp lệ, server từ chối hoặc chưa xác định kết quả; đọc Serial |

- LEFT/RIGHT trong chế độ làm bài không đổi câu, không xóa lựa chọn.
- MODE vẫn vào nhập ID; MODE lần nữa chuyển sang phòng.
- LEFT trong chế độ nhập vẫn hủy phần đang nhập.
- Khi đổi câu, đóng/mở lại câu hoặc đổi số phương án, lựa chọn chưa gửi bị xóa.
- Nhận lại cùng STATE không xóa lựa chọn đang nhập.
- Khi đang chờ kết quả, các phím chọn đáp án và MODE bị khóa như trước.
- Gói đang chờ kết quả giữ nguyên câu/sequence/đáp án, kể cả giáo viên chuyển
  sang câu khác. ACK câu cũ không được biến thành ACK câu mới.
- Mất kết nối hoặc đổi phòng xóa trạng thái câu cũ. Remote phải nhận STATE mới.

**Theo câu hiện tại trên web:** STATE mang câu giáo viên đang chọn/chiếu và
trạng thái mở của câu đó. Nếu giáo viên chuyển sang một câu đang đóng, remote
hiện CL (hoặc -- nếu câu chưa được tạo trong buổi), kể cả câu khác còn mở.
Với cách dạy một câu mỗi lần, dùng thao tác mở câu hoặc câu tiếp theo trên web.
Remote không tự chọn câu khác từ OPENMASK và không buộc web đóng mọi câu khác.

Server vẫn quyết định kết quả cuối cùng: nếu câu đóng đúng lúc gói đang truyền,
server có thể trả NACK. LED xanh chỉ sau kết quả chấp nhận chính xác.
STATE là bản chụp trạng thái; không phải bảo đảm câu còn mở tại thời điểm DB xử lý.

## 3. Thử nhanh trên PCB

1. LOGIN ở phòng/ghế hợp lệ. Chưa mở câu: phải thấy -- hoặc CL, bấm A/OK
   không sinh gói ANSWER trong log server.
2. Mở câu 05 có A–D: thấy `n` ↔ `05`; LEFT/RIGHT không đổi số câu.
3. Chọn B nhưng chưa OK; giáo viên mở câu 06: thấy câu 06, lựa chọn B cũ mất.
   Bấm OK lúc này không gửi cho đến khi chọn đáp án mới.
4. Chọn A, chờ hơn 5 giây: cùng trạng thái được phát lại không làm mất lựa chọn.
5. Gửi A và đối chiếu web, log `ACK ANSWER EXACT ... q=6` trên Serial.
6. Đóng câu: thấy CL, bấm đáp án/OK không gửi. Mở lại rồi chọn mới để gửi.
7. Thử đổi câu ngay sau bấm OK: kết quả cũ phải ghi đúng câu cũ; sau đó remote
   theo câu mới và yêu cầu chọn lại.
8. Đổi Room, LOGIN và mở câu ở phòng mới: không giữ câu/lựa chọn của phòng cũ.

Nếu một câu đã có đáp án, muốn sửa phải bật cho phép đổi đáp án trên web.
Room/ID vẫn phải tồn tại và thỏa quy tắc đăng nhập; firmware không tự tạo lớp/ghế.

## 4. Quay lại

Nạp lại `firmware/ARS_remote_v3_11/ARS_remote_v3_11.ino` được giữ nguyên trong gói
để trở về cách chọn câu thủ công. Bridge chuyển phòng V3.12 vẫn dùng được.
Không cần rollback server để quay lại firmware V3.11.

## 5. Kiểm thử và board

- Host C++ chạy mã firmware thật với giả lập phần cứng: đạt các tình huống ở
  `tests/AUTO_QUESTION_RESULTS.md`.
- 19 kiểm thử giao thức/backend và 10 kiểm thử chuyển phòng: đạt.
- Build ARM với Adafruit nRF52 core 1.7.0, target tham chiếu Feather nRF52840:
  Flash 138504 byte (16%), RAM 15752 byte (6%). Đây là kiểm tra biên dịch,
  không xác nhận profile Feather phù hợp để nạp PCB SuperMini.
- Chưa thử bản V3.13 qua Bluetooth/PCB thật. Cần thực hiện bài thử ở trên.

File tham khảo bạn gửi chỉ có dòng `nrf52840 supermini skematic`. Repository
[sasodoma/nrf52840-promicro](https://github.com/sasodoma/nrf52840-promicro)
trong tên file là tài liệu reverse engineering board SuperMini/ProMicro,
không phải profile Arduino đã xác nhận cho PCB của bạn.
Bản này giữ nguyên board_pins, keypad, điều khiển nguồn và transport BLE.

Tài liệu V3.11/V3.12 trong gói được giữ để tham khảo; hướng dẫn không nạp lại
firmware và chọn câu thủ công của các bản đó không áp dụng cho V3.13.
