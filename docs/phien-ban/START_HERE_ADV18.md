# V3.18 — LE 1M cho laptop, giữ firmware V3.17

## Cài lên máy đang chạy V3.17

Giải nén bản này, mở Terminal trong `project`, chạy:

```bash
sudo bash deploy/update_adv18.sh
```

Không nạp lại nRF. Không chạy `install_adv16.sh` hoặc `update_adv17.sh` trong lần nâng cấp này.
Trình cài yêu cầu hai dịch vụ đang hoạt động và adapter `hci0`, đúng máy đã thử.
Nếu thiếu `btmon`, cài gói Ubuntu `bluez`; công cụ đo Serial cần `python3-serial`.

Thành công sẽ có dòng:

```text
ADV18 installed; HCI LE 1M + duplicate filter verified. Backup: /opt/ars-server/backups/adv18-...
```

Xem log:

```bash
journalctl -u ars-ble -u ars-ingest -n 35 --no-pager
```

Mỗi lần `ars-ble` khởi động, bước root ngắn sẽ tắt Coded TX/RX và đọc lại cấu hình;
bridge vẫn chạy bằng tài khoản dịch vụ hiện tại. Log có `ADV18 PHY readback OK`
và `ADV18 running`. Khi cài, trace HCI kiểm tra PHY=0x01, Filter_Duplicates=1;
nếu chưa đạt, trình cài tự chạy rollback và báo vị trí log. Readback PHY mỗi lần
khởi động không thay thế trace HCI; bộ đo bên dưới kiểm tra lại HCI thực tế.

## Đo 100 lần gửi

1. Đóng Serial Monitor và chương trình khác đang giữ cổng USB của remote.
2. Mở **một câu hỏi A/B/C/D trong 15 phút**, bật **cho phép đổi đáp án**.
3. Đặt remote cố định, giữ khoảng cách và Wi-Fi như nhau. Không đổi phòng, ID,
   câu hỏi hoặc phiên học giữa lần đo. Chờ remote nhận trạng thái câu đang mở.
4. Từ `project`, chạy bằng tài khoản thường:

```bash
bash tools/test_adv18_100.sh
```

Cổng khác: `bash tools/test_adv18_100.sh /dev/ttyACM1`.

5. Khi thấy `BAT DAU`, gửi A → OK → chờ ACK; tiếp B, C, D rồi lặp lại.
   Đếm theo `DA GUI n/100`, không đếm số lần nhấn phím chọn đáp án.
6. Thấy `NGUNG BAM` thì ngừng; công cụ tiếp tục ghi 15 giây để nhận ACK cuối.
   Giới hạn tổng thời gian gửi là 10 phút; nếu chưa đủ 100 thì báo cáo sẽ ghi
   `target_reached: false`. Không gọi số giao dịch thiếu ACK lúc hết ghi là mất gói.
7. Gửi đúng file `ARS_ADV18_100_....tar.gz` được in ở cuối. File này chứa Serial,
   HCI và log server cùng đợt; không cần tự ghép các log cũ.

Bộ đo không tự tạo đáp án. Nó khởi động lại bridge để ghi cấu hình HCI, giữ ingest
hoạt động và giữ LE 1M sau phép đo. Ctrl+C lưu log đã đọc và đóng gói kết quả.
Serial được ghi liên tục để giữ phần đã thu nếu chương trình bị ngắt.

## Đã thay đổi gì?

- Thêm `bridge/adv_phy.py`: dùng Bluetooth MGMT tắt cả Coded TX/RX, giữ các bit
  1M/2M và BR/EDR, kiểm tra địa chỉ adapter, đọc lại giá trị sau đổi.
- Thêm drop-in systemd `zzz-adv18-phy.conf`: áp dụng khi dịch vụ khởi động,
  kể cả sau reboot nếu dịch vụ đã được bật tự khởi động. Đây là cấu hình toàn
  adapter hci0, có thể ảnh hưởng các ứng dụng khác muốn dùng Coded PHY.
- Sửa truy vấn trạng thái offline của gateway bằng tham số `LIKE %s`, truyền
  `('BLE ADV16%',)` riêng. Giữ tên port/topic `ADV16` để tương thích giao thức.
- Bridge đổi nhãn phiên bản thành ADV18. Lịch quảng bá, timeout, retry, token,
  quy tắc ACK và firmware đều giữ nguyên V3.17.
- Không sửa `config.ini`, không đổi schema, không xóa hoặc khôi phục dữ liệu DB.

Trình cài lưu bản sao các file sẽ thay, trạng thái PHY và unit hiệu lực **trước**
khi dừng dịch vụ. Backup nằm trong `/opt/ars-server/backups/adv18-...`; không xóa
thư mục này vì bước khởi động dùng thông tin adapter đã lưu ở đó.

## Hoàn tác

Dùng đúng lệnh được trình cài in, ví dụ thay đường dẫn sau bằng backup của bạn:

```bash
sudo bash deploy/rollback_adv18.sh /opt/ars-server/backups/adv18-THOIGIAN-PID
```

Rollback dừng hai dịch vụ, bỏ drop-in V3.18, phục hồi PHY và file bridge/ingest
trước cập nhật, rồi bật dịch vụ. Dữ liệu đáp án mới vẫn được giữ.
Nếu rollback báo lỗi, giữ nguyên backup và gửi log lỗi; không xóa backup.

## Bằng chứng hiện có và giới hạn

Đợt LE 1M lúc 22:51 ngày 14/10/2026: 34 giao dịch đều có phản hồi, 33 chấp nhận,
1 từ chối đúng vì câu đóng; chỉ 1 giao dịch phải retry. Trên 33 đáp án được chấp
nhận: median 597 ms, p95 1172 ms, max 3260 ms. RSSI mạnh hơn đợt trước, nên
không quy toàn bộ cải thiện cho thay đổi PHY. Đây là bằng chứng một remote.

V3.18 tích hợp cách cấu hình đã được thử trên laptop; bản cài đặt mới chưa chạy
trên phần cứng tại môi trường phát triển. Kiểm thử offline ghi ở
`tests/ADV18_RESULTS.md`. Chưa xác nhận tải RF 50 remote; 50 danh tính giả lập
chỉ kiểm tra hàng đợi và nghiệp vụ.

Nguồn kỹ thuật đã đối chiếu: Linux `scan_coded()` kiểm tra TX **hoặc** RX:
https://linux.googlesource.com/linux/kernel/git/torvalds/linux/+/94426e4201fbb1c5ea4a697eb62a8b7cd7dfccbf/include/net/bluetooth/hci_core.h

BlueZ Management API (Get/Set PHY Configuration):
https://github.com/bluez/bluez/wiki/MGMT
