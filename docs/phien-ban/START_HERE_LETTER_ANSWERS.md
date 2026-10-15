# V3.14 — Hiển thị đáp án bằng chữ

Chọn đáp án nào, digit bên phải hiện cố định chữ đó; digit bên trái tắt.
Không còn luân phiên `An` và số 01–10 khi chọn đáp án.

| Phím | Đáp án | LED 7 đoạn |
|---|---|---|
| 1/A | A | A |
| 2/B | B | b |
| 3/C | C | C |
| 4/D | D | d |
| 5/E | E | E |
| 6/F | F | F |
| 7/G | G | G |
| 8/H | H | H |
| 9/I | I | I (hình dạng giống số 1 trên LED 7 đoạn) |
| 0/J | J | J |

B và D dùng chữ thường vì LED 7 đoạn không biểu diễn rõ dạng chữ hoa.
Chỉ được chọn các đáp án có trong câu: câu A–D vẫn không cho chọn E–J.

## Cập nhật

1. Giải nén gói vào thư mục mới.
2. Arduino IDE: mở `firmware/ARS_remote_v3_14/ARS_remote_v3_14.ino` cùng toàn bộ
   các file trong thư mục sketch.
3. Giữ đúng Board/core/cổng USB đã nạp thành công bản trước, rồi Upload.
4. Serial 115200 hiện `ARS Remote V3.14 GATT auto question / letter answers`.
5. Mở câu trên web; remote hiện `n` ↔ số câu. Chọn C: LED hiện C liên tục.
   Bấm OK: hiện gạch chạy chờ ACK; khi nhận kết quả, trở về trạng thái câu.

Nếu server đã dùng bridge V3.12 trở lên, không cần cập nhật server.
Nếu server còn V3.11 và muốn chuyển phòng theo remote, chạy trong thư mục project:

```bash
sudo bash deploy/upgrade_remote_room.sh
```

Tự theo câu giáo viên, khóa câu đóng, Room/ID, BLE, ACK và định dạng gói tin giữ
nguyên. Phòng, ID và số câu vẫn dùng số. `CL`, `--`, `bt`, `LG`, `Er` giữ nguyên.
Hướng dẫn vận hành khác xem `START_HERE_AUTO_QUESTION.md`; phần hiển thị đáp án
bằng số trong tài liệu V3.13 được thay bởi tài liệu này.

## Quay lại

Nạp sketch `firmware/ARS_remote_v3_13/ARS_remote_v3_13.ino` được giữ nguyên trong
gói để quay về đáp án bằng số. Không cần rollback server.

## Xác minh

Đã chạy bộ kiểm thử host C++ của firmware và biên dịch ARM với Adafruit nRF52
core 1.7.0 trên target tham chiếu Feather nRF52840. Target này chỉ dùng kiểm tra
biên dịch; hãy nạp bằng profile SuperMini bạn đang sử dụng thành công.
Chưa kiểm tra bản V3.14 trên PCB thật.
