# BÀN GIAO DỰ ÁN ARS BLE – nRF52840 ↔ Laptop Server

> Mục đích: giúp một người khác có thể tiếp tục phát triển, debug và hoàn thiện dự án mà không cần đọc lại toàn bộ lịch sử trao đổi.

## 1. Mục tiêu dự án

Xây dựng hệ thống Classroom Response System (ARS):

- Mỗi học sinh dùng một Remote chạy nRF52840.
- Laptop Ubuntu làm server.
- Remote gửi câu trả lời bằng BLE Advertising, không pairing, không GATT.
- Laptop nhận bằng Bluetooth tích hợp `hci0`.
- Backend dùng BlueZ, Python bridge `ble_scan.py`, MQTT/Mosquitto, `ars-ingest`, MariaDB và Web UI.
- Mục tiêu hiện tại khi chấm: ưu tiên tối ưu độ ổn định cho **1 Remote duy nhất**.

## 2. Kiến trúc tổng thể

```text
Remote nRF52840
    │ BLE Advertising uplink
    ▼
Laptop Bluetooth hci0
    ▼
BlueZ / bluetoothd
    ▼
ars-ble / ble_scan.py
    ▼
MQTT / Mosquitto
    ▼
ars-ingest
    ▼
MariaDB
    ▼
Web UI

Chiều ngược lại:
ars-ingest → MQTT → ble_scan.py → BLE Advertising ACK/STATE/ATTEND/OPENMASK → nRF scan
```

Không dùng Bluetooth pairing, GATT Service/Characteristic hay Wi-Fi giữa Remote và laptop.

## 3. Phần cứng Remote đã xác nhận

Board: nRF52840 SuperMini / ProMicro.

### 3.1 GPIO keypad

```cpp
ROW_1 = NRF_GPIO_PIN_MAP(1, 13); // P1.13 / J3.9
ROW_2 = NRF_GPIO_PIN_MAP(1, 11); // P1.11 / J3.10
ROW_3 = NRF_GPIO_PIN_MAP(0, 10); // P0.10 / J3.11
ROW_4 = NRF_GPIO_PIN_MAP(0, 9);  // P0.09 / J3.12

COL_1 = NRF_GPIO_PIN_MAP(0, 31); // P0.31 / J3.5
COL_2 = NRF_GPIO_PIN_MAP(0, 29); // P0.29 / J3.6
COL_3 = NRF_GPIO_PIN_MAP(0, 2);  // P0.02 / J3.7
COL_4 = NRF_GPIO_PIN_MAP(1, 15); // P1.15 / J3.8
```

### 3.2 Toàn bộ pin chính

```text
EXT_VCC P0.13
SEG_A P0.06
SEG_B P0.08
SEG_C P0.17
SEG_D P0.20
SEG_E P0.22
SEG_F P0.24
SEG_G P1.00
DIG1 P0.11
DIG2 P1.04
STATUS P1.06
ROW1 P1.13
ROW2 P1.11
ROW3 P0.10
ROW4 P0.09
COL1 P0.31
COL2 P0.29
COL3 P0.02
COL4 P1.15
```

### 3.3 LED 7 đoạn

- 2 digit.
- Common anode.
- Chọn digit qua transistor PNP 2N3906.
- Digit active LOW.

### 3.4 Key mapping

```text
S1=A, S2=B, S3=LEFT, S4=C
S5=D, S6=E, S7=RIGHT, S8=F
S9=G, S10=H, S11=MODE, S12=I
S13=J, S14=OK, S15/S16=NONE
```

A–J chọn đáp án, LEFT/RIGHT đổi câu, MODE vào cấu hình Room/Seat, OK lưu/gửi.

## 4. Protocol uplink từ nRF lên server

Remote tự tạo protocol ARS 9 byte rồi đặt vào BLE Manufacturer Data.

```text
[0] A5
[1] type
[2] room
[3] seat
[4] question
[5] seq
[6] answer
[7] battery low
[8] battery high
```

Type:

```text
1 = LOGIN
2 = ANSWER
```

Answer:

```text
0=none, 1=A, 2=B, 3=C, ... 10=J
```

Manufacturer Company ID:

```text
0xFFFF
```

Server coi packet là packet ARS khi Company ID = `0xFFFF` và byte đầu payload = `0xA5`.

Ví dụ Room 1, Seat 2, Question 1, Seq 55, Answer C:

```text
A5 02 01 02 01 37 03 xx xx
```

## 5. Cách nRF gửi packet

Firmware hiện tại:

```cpp
ADV_INTERVAL_UNITS = 40;
TX_BURST_MS = 150;
```

BLE dùng đơn vị 0.625 ms nên:

```text
40 × 0.625 ms = 25 ms
```

Tức advertising event khoảng mỗi 25 ms. Trong burst 150 ms có khoảng 6 advertising events.

Workflow:

```text
Button OK
  ↓
Tạo ARS packet
  ↓
Scanner nRF OFF
  ↓
BLE advertise 150 ms
  ↓
Advertising OFF
  ↓
Scanner nRF ON
  ↓
Chờ ACK 1000 ms
```

Remote dùng `ADV_NONCONN_IND`, non-connectable, non-scannable, LE 1M PHY.

## 6. Retry phía nRF

```cpp
ACK_LISTEN_MS = 1000;
MAX_ATTEMPTS = 4;

BACKOFF_MS[3][2] = {
    {50,150},
    {150,400},
    {300,800}
};
```

Retry dùng cùng `seq`, không tạo seq mới.

## 7. Downlink từ server về nRF

Frame types:

```text
0x10 STATE
0x11 ATTEND
0x12 OPENMASK
0x13 ACKS
```

STATE:

```text
[A5,10,room,qid,open,n_options] + 13-byte answered bitmap
```

LOGIN hiện xác nhận qua ATTEND bitmap, chưa có exact LOGIN ACK riêng.

Exact ANSWER ACK record:

```text
seat
question
seq
answer_code
status
```

`status=0` là OK.

Remote chỉ xác nhận khi seat, question, seq, answer đều đúng và status=0.

## 8. Server stack

Source:

```text
~/Documents/IOT2026/ars-server-main2/ars-server-main
```

Runtime:

```text
/opt/ars-server
```

Config:

```text
/opt/ars-server/config.ini
```

Services:

```text
apache2      active
mariadb      active
mosquitto    active
bluetooth    active
ars-ingest   active
ars-ble      active
ars-mdns     active
ars-bridge   inactive (expected)
```

Command hay dùng:

```bash
ars status
ars logs
journalctl -u ars-ingest -f --since now
journalctl -u ars-ble -f --since now
sudo ars ble
ars sim 1 1
ars restart
```

Lưu ý: `sudo ars ble` chỉ dump packet, không publish MQTT và không phát ACK end-to-end.

## 9. Luồng packet phía laptop

```text
nRF BLE Advertising
↓
hci0
↓
BlueZ
↓
ble_scan.py
↓
MQTT
↓
ars-ingest
↓
MariaDB
```

Mốc debug quan trọng:

```text
TX ANSWER
```

=> nRF đã tạo transaction.

```text
DIAG RF RX ANSWER
```

=> laptop đã nhận được BLE packet.

```text
NHẬN ghế 02...
```

=> MQTT + ingest đã xử lý.

```text
ACK ADV START
```

=> server bắt đầu phát exact ACK.

```text
ACK ANSWER EXACT
```

=> nRF đã nhận ACK thành công.

## 10. BlueZ / HCI / btmon

`hci0` là Bluetooth controller của laptop.

Kiến trúc:

```text
Python
↓ D-Bus
BlueZ
↓
Linux Bluetooth
↓ HCI
hci0
↓
2.4 GHz RF
```

Dùng `btmon` để xem HCI thật:

```bash
sudo btmon -w ~/trace.btsnoop
sudo btmon -r ~/trace.btsnoop
```

## 11. Root cause lớn đã tìm được

Trước đây Python yêu cầu:

```text
ACK interval = 20–30 ms
```

nhưng HCI thực tế lại dùng:

```text
1280 ms
```

Nguyên nhân: `/etc/bluetooth/main.conf` đang comment dòng experimental:

```ini
#Experimental = true
```

BlueZ 5.72 coi `MinInterval` và `MaxInterval` là experimental property.

Sau khi sửa:

```ini
[General]
Experimental = true
```

và restart Bluetooth, `btmon` xác nhận HCI thực sự dùng:

```text
Min advertising interval: 20 ms
Max advertising interval: 30 ms
```

### Cấu hình này phải giữ nguyên

```bash
grep -nEi "Experimental" /etc/bluetooth/main.conf
```

phải thấy:

```text
Experimental = true
```

Sau khi chỉnh BlueZ:

```bash
sudo systemctl restart bluetooth
sleep 3
sudo systemctl restart ars-ble
```

## 12. Kết quả V3.10.4 sau khi fix BlueZ

Test seq 15 → 48:

```text
34 logical ANSWER
Server RX = 32/34 = 94.1%
Final ACK = 32/34 = 94.1%
ACK / server-received = 32/32 = 100%
Timeout = seq18, seq20
```

Hai timeout không có `DIAG RF RX`.

Kết luận:

```text
Downlink ACK khi server đã nhận packet: rất tốt.
Vấn đề còn lại: uplink nRF → laptop đôi khi miss.
```

Nhược điểm: ACK burst 850 ms dài, nhiều retry, first-attempt success thấp.

## 13. V3.10.5 Single Remote

Thông số:

```text
ACK interval       20–30 ms
ACK burst          300 ms
ACK align          80 ms
ACK rearm gap      450 ms
ATTEND burst       350 ms
STATE              120 ms
OPENMASK           120 ms
Background refresh 60 s
Scan               continuous
```

Kết quả seq 53 → 61:

```text
9 transaction

Server RX:
55
57
58
59
61

=> 5/9 = 55.6%

Final ACK:
5/5 server-received = 100%

Timeout:
53
54
56
60
```

Các timeout này không có `DIAG RF RX`.

RSSI packet nhận được khoảng `-48` đến `-57 dBm`, tức rất mạnh.

Kết luận:

```text
ACK 300 ms đủ tốt.
Không cần quay lại 850 ms.
Bottleneck hiện tại là uplink nRF → laptop.
```

## 14. V3.10.6 Single Exclusive

Đây là hướng đang chuẩn bị test tiếp.

Lý do: thầy chỉ chấm 1 Remote, nên không cần laptop vừa scan vừa advertise trong cùng lúc.

Workflow dự kiến:

```text
IDLE:
Laptop = SCAN ONLY

Nhận ANSWER:
  ↓
xử lý backend
  ↓
align ~80 ms
  ↓
STOP SCAN
  ↓
ACK-only 300 ms @ 20–30 ms
  ↓
START SCAN lại
```

Thông số dự kiến:

```text
ACK interval       20–30 ms
ACK align          80 ms
ACK burst          300 ms
ACK exclusive      ~340 ms
ATTEND burst       350 ms
ATTEND exclusive   ~390 ms
Background refresh 60 s
Firmware nRF       V3.10
TX burst nRF       150 ms
```

File đã tạo:

```text
ble_scan_v3_10_6_single_exclusive.py
ble_scan_v3_10_6_single_exclusive.patch
```

Trạng thái:

```text
ĐÃ TẠO
CHƯA CÓ KẾT QUẢ TEST THỰC TẾ trong tài liệu này
```

## 15. Vấn đề hiện tại

### 15.1 Uplink miss

Biểu hiện:

Remote:

```text
TX ANSWER
RETRY
RETRY
ACK TIMEOUT
```

Server:

```text
không có DIAG RF RX
```

=> packet chưa tới tầng Python/server.

Không phải lỗi DB, MQTT, ingest hay ACK generation.

Khả năng liên quan:

- timing scan/advertise trên cùng `hci0`
- Bluetooth controller scheduling
- background advertising làm gián đoạn scan
- TX burst nRF 150 ms chưa đủ ổn định
- BlueZ discovery scheduling
- active scan / controller behavior

### 15.2 First-attempt success còn thấp

Sau khi fix BlueZ, final ACK khi server đã nhận packet rất tốt nhưng nhiều transaction vẫn phải retry.

Mục tiêu cho 1 Remote:

```text
First-attempt success >= 90%
Final ACK ~100%
Timeout ~0
```

### 15.3 LOGIN

LOGIN dùng ATTEND bitmap thay vì exact ACK có seq. Đây là handshake yếu hơn ANSWER nhưng chưa phải ưu tiên số 1.

## 16. Hướng tiếp tục

### Bước A – Test V3.10.6 Single Exclusive

```bash
cd ~/Documents/IOT2026/ars-server-main2/ars-server-main

cp bridge/ble_scan.py bridge/ble_scan.py.v3_10_5_backup

cp ~/Downloads/ble_scan_v3_10_6_single_exclusive.py bridge/ble_scan.py

sudo cp bridge/ble_scan.py /opt/ars-server/bridge/ble_scan.py

sudo python3 -m py_compile /opt/ars-server/bridge/ble_scan.py

sudo systemctl restart ars-ble
```

Kiểm tra:

```bash
journalctl -u ars-ble -n 20 --no-pager
```

Đợi service ổn định khoảng 2 giây rồi test.

Mục tiêu:

```text
20 ANSWER
Server RX 20/20
Final ACK 20/20
Timeout 0
First-attempt >= 90%
```

### Bước B – Nếu V3.10.6 vẫn miss uplink

Nếu Remote timeout nhưng server không có `DIAG RF RX`, tối ưu Remote:

```text
TX_BURST_MS:
150 ms
↓
220–250 ms
```

Ví dụ:

```cpp
static constexpr uint32_t TX_BURST_MS = 250;
```

Khi đó:

```text
250 / 25 ≈ 10 advertising events
```

thay vì khoảng 6 event.

Vì chỉ có 1 Remote nên không cần lo collision giữa nhiều thiết bị.

### Bước C – Nếu vẫn chưa đủ

Dùng `btmon` để kiểm tra scan scheduling:

```bash
sudo btmon -w ~/ars_test.btsnoop
```

sau vài transaction:

```bash
sudo btmon -r ~/ars_test.btsnoop
```

Xem:

- scan enable/disable
- advertising enable/disable
- discovery stop/start
- interval thực tế
- thời điểm packet nRF xuất hiện

## 17. Cách phân loại lỗi

### Uplink miss

Remote:

```text
TX ANSWER seq=60
...
ACK TIMEOUT
```

Server không có:

```text
DIAG RF RX seq=60
```

=> uplink miss.

### Downlink miss

Server có:

```text
DIAG RF RX
DIAG ACK QUEUED
DIAG ACK ADV START
```

Remote vẫn timeout.

=> downlink ACK miss.

### Thành công sau retry

Server thấy lại cùng seq và Remote cuối cùng báo:

```text
ACK ANSWER EXACT
```

=> delayed delivery / delayed ACK.

## 18. Điều không nên làm

Không tăng TX power bừa vì RSSI đang rất tốt.

Không tăng ACK timeout lên vài giây vì ACK 300 ms @ 20–30 ms đã đủ khi server nhận packet.

Không debug database khi không có `DIAG RF RX`.

Không dùng `sudo ars ble` để test end-to-end ACK.

Không xóa `Experimental = true`.

## 19. Cách đánh giá mỗi version

Mỗi test ghi:

```text
Total unique ANSWER
Unique server RF RX
Final ACK
First-attempt success
Retry-success
Timeout
```

Công thức:

```text
Uplink reliability
= server unique RX / total unique TX

Final reliability
= final ACK / total unique TX

Downlink reliability after server RX
= final ACK / server unique RX
```

Ví dụ V3.10.5:

```text
total = 9
server RX = 5
final ACK = 5

uplink = 5/9 = 55.6%
downlink after RX = 5/5 = 100%
```

## 20. Mục tiêu cuối cho bài chấm 1 Remote

Không cần tối ưu nhiều Remote trước.

Mục tiêu:

```text
1 Remote
Room 1 Seat 2
4 đáp án A/B/C/D
```

Yêu cầu:

```text
Server RX >= 98%
Final ACK >= 98%
Timeout gần 0
First-attempt >= 90%
Không cần pairing
Không cần GATT
UI phản hồi đúng
DB lưu đúng
```

Nếu đạt `20/20`, `29/30` hoặc `30/30` thì đủ mạnh để trình diễn.

## 21. Checklist trước khi test

```bash
systemctl is-active bluetooth
systemctl is-active ars-ble
systemctl is-active ars-ingest
systemctl is-active mosquitto
systemctl is-active mariadb
```

Kiểm tra:

```bash
grep -nEi "Experimental" /etc/bluetooth/main.conf
```

Phải thấy:

```text
Experimental = true
```

Mở log:

```bash
journalctl -u ars-ble -f --since now
journalctl -u ars-ingest -f --since now
```

Remote:

```text
room = 1
seat = 2
question = 1
```

Sau đó test A/B/C/D.

## 22. Tóm tắt bàn giao

Tình trạng:

```text
Hardware Remote          OK
Keypad mapping           OK
7-seg                    OK
BLE protocol             OK
Server backend           OK
MQTT                     OK
MariaDB                  OK
Exact ANSWER ACK         OK
BlueZ 20–30 ms interval  FIXED
Downlink after server RX rất tốt
```

Vấn đề còn lại:

```text
Uplink nRF → laptop đôi khi miss.
```

Ưu tiên tiếp theo:

```text
1. Test V3.10.6 Single Exclusive
2. Nếu vẫn miss uplink:
   tăng TX_BURST_MS nRF từ 150 → 220–250 ms
3. Test lại 20–30 transaction
4. Nếu vẫn chưa ổn mới dùng btmon sâu hơn
```

Mục tiêu hiện tại:

```text
Không scale nhiều Remote.
Tối ưu 1 Remote cho bài chấm.
```

## 23. Quy tắc quan trọng cho người tiếp tục dự án

Nếu thấy `TX ANSWER` nhưng không thấy `DIAG RF RX`:
=> debug RF/uplink.

Nếu thấy `DIAG RF RX` nhưng Remote timeout:
=> debug ACK/downlink.

Nếu thấy `NHẬN`:
=> MQTT + ingest đã đi qua.

Nếu thấy `ACK ANSWER EXACT`:
=> transaction hoàn thành.

Đừng sửa nhiều biến cùng lúc. Mỗi version chỉ nên thay một nhóm timing/radio logic rồi đo lại.
