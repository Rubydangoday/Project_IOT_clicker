> Tài liệu lịch sử V3.16. Với mã trong gói V3.17, ưu tiên START_HERE_ADV17.md. Máy đang chạy ADV16 dùng update_adv17.sh, không cài lại từ đầu.

# V3.16 — BLE advertising thử nghiệm, thiết kế hướng tới 50 remote

**Đây là nhánh thử nghiệm riêng. V3.15 GATT vẫn là bản đã được bạn thử thành công
trên PCB.** V3.16 đã được kiểm thử phần mềm và biên dịch ARM; chưa được chạy trên
adapter laptop/PCB của bạn. Demo một remote không chứng minh tải vô tuyến 50 remote.

## 1. Những gì đã thay đổi

- ANSWER/LOGIN truyền trong advertising Manufacturer Data, không kết nối GATT,
  không dùng NUS, không yêu cầu MTU hay BLE pairing trong bản thử nghiệm này.
- Magic mới A6 tách khỏi bản A5 cũ. Uplink 21 byte; ACK tối đa hai kết quả/gói.
- Mỗi giao dịch mới có token ngẫu nhiên 64 bit lấy từ SoftDevice, gắn với phiên
  học, thiết bị, phòng, ID, loại giao dịch, câu, seq và đáp án. Retry giữ nguyên token.
- Backend lưu kết quả giao dịch vào bảng `adv_transactions` cùng transaction DB
  với LOGIN/ANSWER. Chỉ publish ACK sau commit; lỗi/rollback không tạo ACK thành công.
- Retry sau mất ACK hoặc sau khởi động lại backend đọc kết quả đã lưu, không ghi
  lại đáp án. Heuristic seq 8 bit/10 giây của bản cũ không dùng cho ADV16.
- Bridge có hàng đợi ACK 512 giao dịch, TTL 20 giây; hai kết quả/trang, phát luân
  phiên công bằng, không chỉ giữ bốn kết quả mới nhất. Khi cùng remote bắt đầu
  giao dịch mới, ngừng phát ACK của giao dịch cũ đó. Không loại ACK của remote khác.
- Bridge không chủ động dừng scanner để trả ACK. Adapter vẫn tự chia lịch RX/TX;
  không có nghĩa một radio có thể phát và thu đúng cùng một thời điểm.
- Giữ nhập Room/ID, đáp án bằng chữ, tự theo câu giáo viên, báo lỗi và nghỉ màn
  hình. Không dùng địa chỉ của một remote cố định trong config để lọc thiết bị.

## 2. Cài đặt trên laptop đang có V3.12 GATT

Giải nén vào thư mục mới, mở terminal tại thư mục `project` của V3.16.
Không chạy `install_ubuntu.sh` để nâng cấp; không chép config.ini mẫu đè cấu hình thật.

Kiểm tra môi trường trước:

```bash
python3 -c 'import bleak, dbus_fast, pymysql, paho.mqtt.client'
sudo python3 bridge/ble_adv.py --config /opt/ars-server/config.ini --check
```

`--check` đọc khả năng advertising của adapter; chưa kiểm tra được thông lượng,
quyền của tài khoản dịch vụ khi chạy thật hay việc interval yêu cầu có được áp dụng.
Nếu thiếu module, dừng tại đây và xử lý đúng môi trường `/usr/bin/python3` của
service. Các gói thường dùng trên Ubuntu gồm python3-bleak, python3-paho-mqtt,
python3-pymysql, python3-serial, mariadb-client; dbus_fast cần có theo môi trường
Bleak/Ubuntu cụ thể. Không thay Python của service một cách tùy ý.

Cài bản thử nghiệm:

```bash
sudo bash deploy/install_adv16.sh
```

Script thực hiện:

1. Kiểm tra dịch vụ hiện tại là GATT, phụ thuộc Python và API advertising.
2. Sao lưu source/config vào `server-before.tar.gz`, toàn bộ DB vào
   `database-before.sql.gz`, và ghi cấu hình dịch vụ trong thư mục root-only:
   `/opt/ars-server/backups/adv16-THOIGIAN-PID/`.
3. Kiểm tra các bảng nghiệp vụ cần thiết dùng InnoDB. Dừng dịch vụ và thêm bảng
   `adv_transactions`; không xóa/đổi cấu trúc các bảng đang có.
4. Dùng drop-in `zz-adv16.conf` để chuyển `ars-ble` sang `ble_adv.py` và
   `ars-ingest` sang `ingest_adv.py`. Nếu lỗi cài đặt, thử rollback tự động.

Xác nhận dịch vụ:

```bash
systemctl show ars-ble -p ExecStart --no-pager
systemctl show ars-ingest -p ExecStart --no-pager
journalctl -u ars-ble -u ars-ingest -f
```

Phải thấy entrypoint mới và dòng `ADV16 running`. Service active chỉ chứng minh
process đang chạy; vẫn phải làm thử nghiệm hai chiều bên dưới.

## 3. Nạp firmware và thử một remote

1. Arduino IDE: mở `firmware/ARS_remote_v3_16/ARS_remote_v3_16.ino`, giữ đủ file
   .h/.cpp trong thư mục. Giữ đúng Board/core/bootloader/cổng đã nạp được V3.15.
2. Upload, Serial Monitor 115200 phải hiện:
   `ARS Remote V3.16 ADV experimental / letter answers`.
3. Trên web, bắt đầu **buổi học thử**, đặt đúng phòng và có ID học sinh hợp lệ.
   Remote cần nhận STATE của một buổi học đang chạy để gửi LOGIN.
4. Đặt Room/ID trên remote. Khi LOGIN được xác nhận, mở câu A–D, chọn B, bấm OK.
5. Kiểm tra đồng thời: remote báo kết quả, web có B, backend có `ADV COMMIT` và
   bridge có `ADV RESULT` với cùng token. Không chỉ dựa vào màu đèn.

Không thấy remote trong lệnh quét GATT/NUS là bình thường: ADV16 không quảng bá
NUS để kết nối. Không chạy bridge GATT và bridge advertising cùng lúc trên hci0.

Serial chính:

```text
ADV STATE READY
ADV_BEGIN token=... type=1
ACK LOGIN EXACT: OK
ADV_BEGIN token=... type=2
ADV_METRIC token=... type=2 status=0 elapsed_ms=... attempts=...
```

`status=0`: backend đã commit/chấp nhận đúng giao dịch. 1..255: NACK nghiệp vụ.
`256`: timeout, kết quả chưa rõ. `257`: mất/đổi STATE khi đang chờ, kết quả chưa rõ.
Khi chưa rõ, kiểm tra web trước khi bấm lại tạo giao dịch mới.

## 4. Đo tốc độ thật — không dùng số giả lập làm benchmark

Đóng Serial Monitor của Arduino để tránh hai chương trình giữ cùng cổng.
Tại thư mục project:

```bash
python3 tools/adv_measure.py --port /dev/ttyACM0 --seconds 300 --output adv_demo
```

Chọn đúng cổng thực tế. Công cụ cần pyserial (`python3-serial` trên Ubuntu).
Trong thời gian ghi, bấm đáp án trên remote bằng tay trong một câu thử đang mở.
Muốn gửi nhiều lần cùng câu, bật cho phép đổi đáp án trong buổi học thử. Không
bật tính năng này trong buổi thi thật chỉ để đo hiệu năng.

Kết quả: `adv_demo.log`, `adv_demo.csv`, `adv_demo.json`.
Hoặc phân tích log Serial đã lưu:

```bash
python3 tools/adv_measure.py --log serial.log --output adv_demo
```

Công cụ báo số ANSWER bắt đầu, nhận thành công, bị từ chối, chưa rõ, chưa đủ log,
median/p95/max của các ANSWER được chấp nhận. Độ trễ do firmware đo từ lần bắt
đầu gửi giao dịch đến khi xử lý kết quả; bao gồm retry. Không gồm thời gian người
nghĩ/chọn đáp án và chống dội phím trước khi ứng dụng nhận phím OK.

Để xác minh chính xác, đối chiếu token trong Serial với `ADV COMMIT`, nội dung
trên web/DB. Capture bắt đầu giữa giao dịch có thể thiếu BEGIN; công cụ báo
orphan/incomplete thay vì coi là mất gói. Nếu nguồn entropy không sẵn sàng suốt
mọi lần thử thì chưa có token/BEGIN; xem cả log TX QUEUE FAILED và ACK TIMEOUT.

Không dùng `rx_to_backend_ms` của bridge làm độ trễ toàn trình: nó chưa tính
thời gian quảng bá kết quả và remote nhận ACK. Số ping GATT ~96 ms trước đây cũng
không phải phép đo cùng loại.

## 5. Thử mất gói có chủ đích trên laptop

Giữ `ars-ingest` chạy, chỉ dừng bridge dịch vụ rồi chạy bridge foreground:

```bash
sudo systemctl stop ars-ble
sudo -u ars /usr/bin/python3 /opt/ars-server/bridge/ble_adv.py \
  --config /opt/ars-server/config.ini --drop-uplink-every 3
```

Mỗi giao dịch mới thứ ba sẽ bị bỏ các bản sao uplink trong 0,8 giây đầu. Remote
phải retry cùng token. Đây là bỏ gói sau khi laptop đã thu, không phải gây nhiễu RF.
Sau khi thử, Ctrl+C. Thử bỏ kết quả đầu tiên của mỗi giao dịch thứ ba:

```bash
sudo -u ars /usr/bin/python3 /opt/ars-server/bridge/ble_adv.py \
  --config /opt/ars-server/config.ini --drop-result-every 3
```

DB có thể đã lưu dù ACK bị bỏ. Sau retry, phải chỉ có một đáp án cho cùng giao
 dịch. Đọc ledger để đối chiếu; không được nhầm các lần OK mới thành retry.
Kết thúc Ctrl+C rồi:

```bash
sudo systemctl start ars-ble
```

Các tùy chọn bỏ gói chỉ áp dụng khi chạy tay; installer không bật chúng.

## 6. Kiểm thử 50 thiết bị giả lập

Kiểm thử offline, không đụng DB thật, không cần 50 mạch:

```bash
python3 tests/adv_unit.py
bash tests/adv_firmware_host/run.sh
```

Có bài 50 LOGIN + 50 ANSWER, mỗi ANSWER lặp năm lần; kết quả mong đợi chỉ 50
responses. Có bài công bằng ACK cho 50 danh tính. Cả hai KHÔNG mô phỏng va chạm RF.

Muốn thử MQTT + MariaDB thật: tạo lớp thử tên bắt đầu bằng `ADV16_TEST`, có ghế
1..50, một buổi đang chạy và một câu đang mở. Công cụ dưới đây sẽ ghi dữ liệu thật
vào lớp thử đó, không tự tạo/xóa lớp và không đo Bluetooth:

```bash
python3 tools/adv_backend_load.py --config /opt/ars-server/config.ini \
  --test-session ID_BUOI_THU --room SO_PHONG --question SO_CAU --devices 50 --copies 3
```

Thay các giá trị chữ bằng số thật. Dùng danh tính MAC giả `C2:16:00:00:00:01` đến
`:32`; không gán mapping của remote thật cho lớp thử này. Khi lặp lại bài thử trên
cùng câu cần cho phép đổi đáp án hoặc tạo buổi thử mới.

## 7. Giới hạn và tham số ban đầu

- Radio remote: advertising non-connectable/non-scannable, interval yêu cầu
  100 ms, đợt TX 240 ms, trễ ban đầu ngẫu nhiên 0..200 ms. Scanner vẫn hoạt động.
- Chờ ACK 2,5 s/lần, tối đa sáu lần; backoff tăng ngẫu nhiên 100..1200 ms.
  Khi hết hạn, dừng và báo chưa rõ kết quả. Không phát vô hạn.
- Laptop: yêu cầu interval 100 ms; mỗi trang giữ 180 ms, dành một lượt STATE
  khoảng mỗi giây khi có ACK. Có chi phí unregister/register D-Bus giữa các trang.
- 50 kết quả cần ít nhất 25 trang ACK. Riêng thời gian giữ trang là **4,5 giây**;
  cộng STATE, D-Bus và mất gói có thể lâu hơn. Đây là cấu hình bảo thủ để kiểm thử,
  **không cam kết 50 remote nhận ACK trong 500 ms hoặc 2 giây**.
- Đích thử tải đầu tiên là 50 remote trong một phòng. Bridge nhận Room từ payload
  và phát STATE các phòng hoạt động; năng lực nhiều phòng đồng thời chưa được xác nhận.
- Máy quét laptop dùng active discovery để tương thích BlueZ cũ; remote là
  non-scannable nên không dựa vào scan response. Không có scan pause trong mã ứng
  dụng, nhưng adapter/BlueZ có thể vẫn chia thời gian, bỏ lọt gói hoặc lọc báo cáo.
- Dùng `sudo btmon` khi chạy bridge để kiểm tra lệnh cấu hình interval thực tế.
  `interval_requested_ms=100` trong log chỉ là yêu cầu. Một số phiên bản BlueZ cũ
  cần hỗ trợ experimental cho interval; không tự bật/tắt bluetoothd trong installer.
- Nghỉ sau 30 giây vẫn tắt LED và cho vòng CPU delay 20 ms. **Scanner radio vẫn
  quét liên tục** để nhận STATE/ACK; không có mức tiết kiệm radio như GATT connected
  idle. Chưa đo dòng PCB. Nếu mất STATE 15 giây, remote thoát nghỉ/bỏ trạng thái cũ.
- Token chống nhầm/trùng giao dịch, không phải xác thực hay mã hóa. Bản thử nghiệm
  không chống thiết bị chủ động giả mạo/quay lại traffic; chỉ dùng trong môi trường
  demo tin cậy. Company ID FFFF dùng cho thử nghiệm, không phải mã công ty đăng ký.
- Bảng ledger giữ lại để chống replay do retry; không tự xóa sau 10 giây. Quy tắc
  lưu trữ/dọn dữ liệu dài hạn cần thiết kế khi chuyển sang vận hành thật.

## 8. Quay lại bản GATT đang ổn định

Dùng đúng đường dẫn backup installer vừa in:

```bash
sudo bash deploy/rollback_adv16.sh /opt/ars-server/backups/adv16-THOIGIAN-PID
```

Sau đó nạp `firmware/ARS_remote_v3_15/ARS_remote_v3_15.ino`.
Rollback khôi phục dịch vụ trước đó và base ingest, giữ config hiện tại, các đáp án
mới và ledger. Không tự nạp SQL backup đè DB đang chạy. Không chạy bridge GATT với
firmware ADV16 hoặc ngược lại.

## 9. Cách báo cáo đúng với thầy

“Em xây dựng nhánh BLE advertising với mã giao dịch, ACK tầng ứng dụng, retry và
lưu kết quả chống trùng bền vững. Phần mềm đã kiểm thử 50 danh tính giả lập. Em
đo thực tế trên một remote; chưa kết luận thông lượng vô tuyến cho 50 thiết bị.”

Sau khi chạy, gửi `adv_demo.json` và log của hai dịch vụ để quyết định chỉnh
interval/cửa sổ ACK. Nếu adapter laptop không đáp ứng RX/TX, hướng tiếp theo là
bộ thu nRF USB để chủ động lịch radio, không khẳng định phần cứng laptop đã đủ.

Chi tiết kiểm thử: `tests/ADV16_RESULTS.md`.
