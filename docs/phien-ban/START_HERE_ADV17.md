# V3.17 — sửa lịch phát/nhận cho bản advertising thử nghiệm

**Dành cho máy đang chạy V3.16 ADV16, như log bạn gửi. Cần cập nhật cả laptop
và firmware nRF.** Giữ nguyên PCB, cấu hình phòng/ID, MariaDB, MQTT và giao thức
A6. Đây là bản sửa để đo lại trên phần cứng, chưa phải kết quả RF đã xác nhận.

## Vì sao cần sửa?

Đợt đo ngày 14/10/2026 của bạn có bốn đáp án được chấp nhận:

| Đáp án | Remote bắt đầu giao dịch → nhận kết quả | Laptop nhận gói → backend trả kết quả |
|---|---:|---:|
| A | 9682 ms | 4,8 ms |
| B | 3016 ms | 7,6 ms |
| C | 16309 ms | 6,6 ms |
| D | 6153 ms | 7,6 ms |

Median toàn giao dịch: 7917,5 ms. Đây là độ trễ quá lớn cho thao tác bấm đáp án.
Backend không phải đoạn chậm chính. Log cũ chưa có timestamp Serial cùng đồng hồ
với server, nên chưa tách chính xác thời gian chờ uplink và downlink.

Trong mã V3.16, laptop giữ STATE quảng bá liên tục khi không có ACK; nRF quét
liên tục trong lúc yêu cầu phát burst 240 ms. Hai vai trò cạnh tranh thời gian
của radio. Đây là giả thuyết cần kiểm tra, không phải kết luận từ RF trace.

## Thay đổi V3.17

- nRF dừng quét trước khi phát; phát burst 400 ms rồi bật quét lại để nghe ACK.
  Burst vẫn có khoảng chờ ngẫu nhiên 0–200 ms. Hết burst không có nghĩa được ACK.
- Laptop vẫn yêu cầu quét liên tục, nhưng chỉ bật quảng bá từng đợt 220 ms rồi
  tắt quảng bá ít nhất 180 ms để dành cơ hội chỉ nhận. STATE tối đa một trang/giây.
  Thời gian thực tế còn phụ thuộc BlueZ/controller và thời gian đăng ký quảng bá.
- ACK vẫn lặp theo hàng đợi; retry giữ nguyên token. Backend chỉ trả kết quả sau
  commit như V3.16. Không giảm timeout để che tình trạng mất gói.
- Thêm `ADV_TX_START`, `ADV_RX_RESUME`, uptime của remote, timestamp UTC khi
  laptop đọc Serial và `ADV ACK_PAGE_REGISTERED` trên server. Mốc đăng ký quảng
  bá không chứng minh gói đã lên sóng; timestamp Serial cũng có độ trễ USB.
- Heartbeat STATE vẫn cập nhật thời hạn sẵn sàng nhưng không in trùng liên tục.
  Nhận lại STATE sau mất sóng vẫn khôi phục câu hỏi. Lỗi khởi động phát/nhận có
  đường phục hồi và giữ nguyên giao dịch đang chờ.

## Cập nhật laptop

Giải nén bản này vào thư mục mới. Mở terminal tại `project` rồi chạy:

```bash
sudo bash deploy/update_adv17.sh
journalctl -u ars-ble -n 25 --no-pager
```

Phải có dòng `ADV17 running` với `downlink pulse=220ms RX-only gap=180ms`.
Script sao lưu bridge cũ rồi chỉ thay `bridge/ble_adv.py` và khởi động lại
`ars-ble`. Không thay config.ini, ingest, bảng dữ liệu hay systemd drop-in.
Không chạy lại `install_adv16.sh` trên máy đã cài ADV16. Lưu đường dẫn backup
và lệnh rollback mà script in ra. Nếu trước đây bạn tự đặt `--page-ms` trong
ExecStart thì giá trị đó vẫn có hiệu lực; kiểm tra dòng startup để biết cấu hình.

## Nạp remote

1. Mở `firmware/ARS_remote_v3_17/ARS_remote_v3_17.ino` bằng Arduino IDE.
2. Giữ board, core, bootloader, cổng nạp đã chạy được trên SuperMini của bạn.
3. Nạp code. Serial 115200 phải có banner V3.17. Đóng Serial Monitor trước khi
   chạy công cụ đo, vì chỉ một chương trình nên đọc cổng Serial tại một thời điểm.
4. Mở phiên học/câu hỏi, kiểm tra đúng phòng và ID, đợi LOGIN thành công.

## Đo lại 30 giao dịch bằng một remote

Mở hai terminal tại thư mục `project` của bản mới.

Terminal 1:

```bash
journalctl --utc -o short-iso-precise -u ars-ble -u ars-ingest --since now -f | tee adv17_server.log
```

Terminal 2 (đổi tên cổng nếu máy bạn dùng cổng khác):

```bash
python3 tools/adv_measure.py --port /dev/ttyACM0 --seconds 300 --output adv17_demo
```

Trên remote: chọn A/B/C/D → OK → chờ kết quả → mới gửi giao dịch tiếp theo.
Thực hiện 30 lần trong lớp thử nghiệm. Công cụ không tự gửi đáp án.
Xem `adv17_demo.json`; gửi lại file này cùng `adv17_demo.log` và
`adv17_server.log`. So khớp token giữa các log, kiểm tra dữ liệu đáp án trên web/DB.

Mục tiêu thử nghiệm đề xuất cho một remote: 30/30 nhận kết quả, không ghi trùng
do retry, không ACK nhầm token, p95 dưới 1,5 giây. Đây là tiêu chí cần đo,
không phải cam kết bản mới đã đạt. Nếu vẫn chậm nhiều giây, cần trace controller:

```bash
sudo btmon -w adv17.btsnoop
```

Chạy đồng thời khi thử vài đáp án rồi Ctrl+C. Trace giúp kiểm tra HCI advertising
reports, lệnh bật/tắt quét/quảng bá và interval controller thực sự nhận. Muốn biết
gói nào mất trên không khí có thể cần sniffer riêng; btmon không thấy mọi gói RF.

## Rollback

Quay lại bridge advertising trước cập nhật bằng đúng đường dẫn script đã in:

```bash
sudo bash deploy/rollback_adv17.sh /opt/ars-server/backups/adv17-THOIGIAN-PID
```

Muốn quay lại toàn bộ lịch radio V3.16 thì nạp lại firmware V3.16.
Nếu cần demo phương án một remote đã ổn định trước đây: dùng
`rollback_adv16.sh` với backup `adv16-...` lúc cài lần đầu, rồi nạp V3.15 GATT.
Không dùng backup `adv17-...` cho script rollback GATT.

## Giới hạn 50 thiết bị

Không có kết luận tải RF 50 remote từ một thiết bị. Mô phỏng 50 danh tính chỉ
kiểm tra backend/hàng đợi. Với 2 kết quả/trang và chu kỳ 220+180 ms, riêng 25
trang ACK đã cần ít nhất 10 giây, chưa tính STATE, D-Bus và mất gói. Khi có đủ
phần cứng phải đo lại, và có thể cần đổi cách đóng gói ACK/lịch truyền hoặc
adapter chuyên dụng. Bản này ưu tiên sửa và đo rõ tình trạng chậm của demo hiện tại.

Kiểm thử và giới hạn: `tests/ADV17_RESULTS.md`.
