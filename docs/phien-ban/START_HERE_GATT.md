> **Gói V3.13:** đọc `START_HERE_AUTO_QUESTION.md` trước. Firmware hiện tại tự theo câu; LEFT/RIGHT không đổi câu. Phần dưới là hướng dẫn lịch sử V3.11. Quy tắc Room cố định chỉ áp dụng cho bridge V3.11.

# ARS V3.11 — 1 remote nRF52840 ↔ laptop Ubuntu bằng BLE GATT

**Đọc file này trước.** Bản mới nằm trong `firmware/ARS_remote_v3_11/` và `bridge/ble_gatt.py`.
V3.10 + `ble_scan.py` vẫn được giữ để quay lại nếu cần. Tài liệu Advertising cũ không áp dụng cho đường GATT.

## 1. Chuẩn bị và nạp firmware

1. Giải nén ZIP và mở Terminal tại thư mục `project` có file này.
2. Trên laptop server, dừng chương trình BLE cũ trước khi thử:

   ```bash
   sudo systemctl stop ars-ble
   sudo systemctl stop ars-bridge
   sudo apt install python3-bleak python3-paho-mqtt python3-pymysql
   ```

3. Trong Arduino IDE, mở **toàn bộ thư mục** `firmware/ARS_remote_v3_11`, chọn file `ARS_remote_v3_11.ino`.
4. Giữ **đúng Board, core và cổng USB đã nạp thành công V3.10 trên SuperMini của bạn**. Không đổi bootloader và không chọn Feather chỉ vì nhìn thấy ví dụ lệnh Feather trong tài liệu cũ.
5. Upload. Serial Monitor = **115200**. GPIO/keypad/7-seg vẫn là cấu hình PCB cũ. Room/Seat đã lưu trong flash tiếp tục dùng được.
6. USB phục vụ nạp/log; dữ liệu đáp án vẫn đi qua Bluetooth. Sau đó thử lại với nguồn vận hành thực của PCB. Chưa có đo pin ADC: trường pin được gửi là **không biết**, không giả lập 3000 mV.

Firmware đã biên dịch thành công với Adafruit nRF52 core 1.7.0 trên target tham chiếu Feather nRF52840; bạn vẫn phải dùng đúng profile SuperMini đã chạy trên PCB. Xem `tests/GATT_RESULTS.md` để biết phạm vi build/test đã thực hiện.

## 2. Thử Bluetooth riêng trước khi ghép backend

Đóng ứng dụng điện thoại/Bluetooth khác đang kết nối remote. Chỉ cho một chương trình giữ kết nối.

```bash
python3 bridge/ble_gatt.py --scan
```

Kết quả cần có `ARS_REMOTE_01`, một địa chỉ MAC và service `6e400001-...`.
Ghi lại MAC thật, ví dụ thay `AA:BB:CC:DD:EE:FF` bên dưới:

```bash
python3 bridge/ble_gatt.py --address AA:BB:CC:DD:EE:FF --probe 100
```

Mục tiêu: `ping_pong_ok: 100`, đồng thời xem `median_ms`, `p95_ms`, `max_ms`.
Đây là đo PING/PONG BLE, **không phải độ trễ ghi database**. Probe không tạo ACK giả, không gửi đáp án lên backend; màn hình `bt` trong phép thử này là bình thường.

Nếu không thấy remote: xác nhận đã nạp V3.11, bật Bluetooth (`rfkill list`), tắt app khác và thử cách laptop 0,5–1 m.
Nếu phát hiện nhiều remote cùng tên, chương trình yêu cầu khai báo MAC, không tự chọn ngẫu nhiên.

## 3. Nối vào server đang có

Sửa **file cấu hình đang chạy**, không chép đè bằng config mẫu:

```bash
sudo nano /opt/ars-server/config.ini
```

Trong section `[ble]` hiện có, thêm/sửa:

```ini
adapter = hci0
remote_name = ARS_REMOTE_01
remote_address = AA:BB:CC:DD:EE:FF
```

`[gateway] room` phải khớp Room trên remote và room của lớp trên web.
Không tạo hai section `[ble]`. Không thay mật khẩu/database của bạn.

Từ thư mục `project` vừa giải nén:

```bash
sudo bash deploy/install_gatt.sh
journalctl -u ars-ble -u ars-ingest -f
```

Script sao lưu ingest, bridge GATT nếu đã có và override service vào `/opt/ars-server/backups/gatt-TIMESTAMP`.
Nó cài bridge mới, bổ sung exact result cho ingest và chuyển `ars-ble` sang `ble_gatt.py`; vô hiệu hóa gateway serial `ars-bridge` để tránh hai gateway chạy đồng thời.
Không đổi database schema, web hoặc config hiện có. **Cần cập nhật ingest đi kèm**; ingest cũ không phát exact LOGIN/ANSWER result cho GATT.

Các mốc log:

- `GATT READY`: kết nối + Notify + HELLO đúng room.
- `GATT RX`: laptop nhận LOGIN/ANSWER.
- `ĐIỂM DANH` / `NHẬN` / `TRÙNG`: backend xử lý.
- `BACKEND RESULT`: bridge nhận kết quả backend có đúng mã yêu cầu.
- Serial remote `ACK LOGIN EXACT`, `ACK ANSWER EXACT`, `RESULT elapsed_ms=...`.

Không dùng `sudo ars ble` cho đường mới: lệnh cũ chỉ quét Advertising. Lệnh `ars logs` hoặc `journalctl` vẫn xem service bình thường.
`Experimental=true` không còn là điều kiện của GATT; có thể giữ nguyên để hỗ trợ quay lại Advertising.

## 4. Hiển thị và phím

LED 7 đoạn có chữ gần đúng: `Id` nhìn gần giống `1d`, `bt` là chữ thường. Mỗi mode số luân phiên nhãn **400 ms** → giá trị **800 ms**; nhập phím hiện giá trị ngay.

| Hiển thị | Ý nghĩa |
|---|---|
| `r` ↔ `01` | Nhập phòng 01 |
| `Id` ↔ `02` | Nhập ghế 02 |
| `n` ↔ `05` | Đang chọn câu 05 |
| `An` ↔ `03` | Đáp án C, quy ước A–J = 01–10 |
| `bt` nhấp nháy | Chưa có kết nối ứng dụng sẵn sàng/đang nối lại |
| Hai dấu gạch chạy trái/phải | Chờ backend xác nhận LOGIN hoặc ANSWER |
| `LG` | Bluetooth sẵn sàng nhưng chưa đăng nhập được; mở buổi học, kiểm tra ghế rồi MODE → OK |
| `Er` khoảng 1,8 giây + đèn đỏ | Bị từ chối hoặc chưa xác định kết quả; đọc Serial/web |

- **MODE**: vào nhập ghế; bấm tiếp chuyển ghế ↔ phòng.
- **OK trong mode nhập**: lưu. Lưu phòng chuyển sang nhập ghế; lưu ghế bắt đầu LOGIN khi BLE sẵn sàng.
- **LEFT trong mode nhập**: hủy phần đang nhập, về màn hình thường. Nếu chưa có ghế thì tiếp tục yêu cầu nhập ghế.
- **LEFT/RIGHT trong mode thường**: đổi câu, xóa lựa chọn đáp án cũ.
- **A–J rồi OK**: chọn và gửi đáp án.
- Mode nhập ưu tiên hiển thị hơn `bt`, để vẫn sửa phòng/ghế khi chưa kết nối.
- Không đổi ghế/câu khi đang chờ kết quả. LED xanh sau LOGIN/ANSWER chỉ báo kết quả được backend chấp nhận. Đèn đỏ/xanh lúc bật nguồn là tự kiểm tra LED.

Nếu chưa tạo/mở buổi học, chưa có học sinh với số ghế đó hoặc MAC đã gán ghế khác, LOGIN sẽ bị NACK có lý do. Đây không phải lỗi Bluetooth.

## 5. Bài kiểm tra chốt demo

1. Mở buổi học, tạo/kiểm tra ghế 02 và mở câu có A–D. Room khớp cả 3 nơi.
2. LOGIN, chờ `ACK LOGIN EXACT`.
3. Gửi 20 câu trả lời đầu tiên. Nếu thử nhiều lần trên cùng một câu, bật cho phép đổi đáp án; nếu không, dùng các câu khác nhau. NACK `NO_CHANGE` khi không cho đổi là hành vi đúng.
4. Sau khi đúng luồng, thử 100 giao dịch, thống kê số ACK/NACK hợp lệ, TIMEOUT và `RESULT elapsed_ms` của Serial. Mục tiêu thử nghiệm: 0 TIMEOUT và ít nhất 95% giao dịch có kết quả dưới 200 ms khi đã kết nối. **Không phải cam kết trước khi đo**.
5. Thử tắt/bật remote 5 lần: tự nối lại và LOGIN lại. Gửi đáp án mới sau LOGIN.
6. Thử ngắt BLE ngay khi đang chờ ACK: không được báo xanh giả. Kết quả có thể đã được lưu trước khi mất kết nối; kiểm tra web. Firmware **không tự phát lại đáp án cũ sau reconnect** để tránh đưa đáp án trễ vào sai thời điểm.
7. Đổi câu, phòng, ghế và kiểm tra từng nhãn màn hình. Cuối cùng thử bằng nguồn vận hành thật của PCB.

Một bài test nhỏ không chứng minh độ tin cậy dài hạn. Chưa có kết quả đo vô tuyến/nguồn/PCB từ môi trường tạo mã này.

## 6. Xử lý nhanh theo triệu chứng

| Triệu chứng | Kiểm tra trước |
|---|---|
| Luôn `bt` | Đã nạp V3.11 chưa, service đang chạy bridge nào, MAC/Room đúng chưa, có app khác giữ kết nối không |
| GATT kết nối nhưng không nhận dịch vụ | Với đúng MAC remote, `bluetoothctl remove AA:BB:CC:DD:EE:FF`, rồi scan lại; tránh dùng cache GATT cũ |
| `LG` / NACK LOGIN | Serial báo NO_SESSION/UNKNOWN_SEAT/MAPPING_MISMATCH…; sửa lớp/buổi/ghế trên web rồi MODE → OK |
| Có `GATT RX`, không có `BACKEND RESULT` | Đã cài ingest mới chưa; kiểm tra `ars-ingest`, MQTT và database |
| Có `BACKEND RESULT`, remote TIMEOUT | Kiểm tra kết nối và log Write/Notify; không tăng công suất RF tùy ý |
| `Er` sau mất kết nối | Kết quả chưa rõ; kiểm tra web trước khi gửi lại bằng một lần bấm mới |
| Quyền truy cập Bluetooth | Chạy probe bằng user thường để đối chiếu; service dùng user `ars`/nhóm bluetooth như cũ, xem journal lỗi D-Bus |

## 7. Quay lại bản trước

Dùng **đường dẫn backup được in khi cài**, từ thư mục project:

```bash
sudo bash deploy/rollback_gatt.sh /opt/ars-server/backups/gatt-TIMESTAMP
```

Nếu quay về Advertising V3.10, nạp lại `firmware/ARS_remote_v3_10/ARS_remote_v3_10.ino`. Server Advertising không giao tiếp được với firmware GATT và ngược lại.

## Tài liệu gốc

- BLE UART/NUS: https://learn.adafruit.com/bluefruit-nrf52-feather-learning-guide/bleuart
- Bleak client: https://bleak.readthedocs.io/en/stable/api/client.html
- Adafruit core 1.7.0: https://github.com/adafruit/Adafruit_nRF52_Arduino/tree/1.7.0
