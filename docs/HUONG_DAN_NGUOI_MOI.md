# HƯỚNG DẪN CHO NGƯỜI MỚI TIẾP NHẬN DỰ ÁN ARS

> Dành cho người **chưa từng thấy** thư mục code này. Không cần biết trước về Bluetooth, MQTT hay nRF52840.
> Đọc từ trên xuống, khoảng 45 phút. Muốn tra cứu kỹ thuật sâu hơn thì xem thêm [`TONG_HOP_DU_AN.md`](TONG_HOP_DU_AN.md).

---

## Mục lục

0. [Hiểu dự án trong 5 phút](#0-hiểu-dự-án-trong-5-phút)
1. [Từ điển: các khái niệm bạn sẽ gặp](#1-từ-điển-các-khái-niệm-bạn-sẽ-gặp)
2. [Bản đồ thư mục: đọc gì, bỏ qua gì](#2-bản-đồ-thư-mục-đọc-gì-bỏ-qua-gì)
3. [Câu chuyện một lần bấm nút](#3-câu-chuyện-một-lần-bấm-nút-đi-qua-từng-file)
4. [Chạy thử lần đầu](#4-chạy-thử-lần-đầu)
5. [Phiên bản: vì sao có nhiều thư mục firmware?](#5-phiên-bản-vì-sao-có-nhiều-thư-mục-firmware-và-tài-liệu-mâu-thuẫn)
6. [Khi có lỗi: tìm ở đâu?](#6-khi-có-lỗi-tìm-ở-đâu)
7. [Sửa code lần đầu: công thức cho việc hay gặp](#7-sửa-code-lần-đầu-công-thức-cho-việc-hay-gặp)
8. [Những cái bẫy cần tránh](#8-những-cái-bẫy-cần-tránh)
9. [Hỏi đáp nhanh](#9-hỏi-đáp-nhanh)
10. [Việc nên làm trong tuần đầu](#10-việc-nên-làm-trong-tuần-đầu)

---

## 0. Hiểu dự án trong 5 phút

### Bài toán

Trong lớp, giáo viên chiếu một câu trắc nghiệm. Mỗi học sinh cầm một **cái remote nhỏ** (giống điều khiển TV), bấm A/B/C/D rồi bấm OK. Ngay lập tức:

- remote của học sinh **sáng đèn xanh** (đã nhận) hoặc **đỏ** (bị từ chối, ví dụ câu đã đóng);
- màn hình giáo viên hiện **ô của học sinh đó chuyển màu**, biểu đồ đáp án tự cập nhật;
- kết quả được **lưu lại** để làm báo cáo, sổ câu sai, gửi phụ huynh…

### Ví von dễ nhớ

| Thành phần thật | Ví như |
|---|---|
| Remote nRF52840 | **Người đưa thư**: chỉ mang phong bì đi, không đọc, không quyết định |
| `bridge/ble_gatt.py` | **Bưu cục**: nhận phong bì qua Bluetooth, chuyển vào hệ thống nội bộ |
| MQTT (Mosquitto) | **Băng chuyền** trong bưu cục, nối các phòng ban |
| `ingest/ingest.py` | **Người kiểm duyệt**: mở phong bì, kiểm tra hợp lệ, ghi sổ, gửi giấy báo nhận |
| MariaDB | **Sổ sách** lưu mọi thứ |
| Web PHP | **Văn phòng** nơi giáo viên, học sinh, phụ huynh xem sổ sách và ra lệnh |

**Quy tắc vàng của dự án:** người đưa thư (remote) và bưu cục (bridge) **không được quyết định gì**. Mọi luật đều nằm ở người kiểm duyệt (`ingest.py`). Muốn đổi luật thì sửa server, không phải nạp lại remote.

### Sơ đồ

```
 [Remote nRF52840] ──Bluetooth──▶ [ble_gatt.py] ──MQTT──▶ [ingest.py] ──SQL──▶ [MariaDB]
        ▲                              │                     │                    ▲
        └────── kết quả, câu đang mở ──┘◀──────MQTT──────────┘                    │
                                                                         [Web PHP trên Apache]
                                                                    giáo viên · màn chiếu · HS · phụ huynh
```

Tất cả chạy trên **một laptop Ubuntu của giáo viên**, không cần Internet.

### Dự án có 2 phần lớn

1. **Phần "bấm remote"** (lõi, khó nhất): firmware C++ + Bluetooth + `ingest.py`. Đây là phần đang được tối ưu, có nhiều phiên bản.
2. **Phần "web học tập"** (LMS): ngân hàng câu hỏi, soạn đề từ Word/Excel, bài giảng, bài tập về nhà, trợ lý AI, thi đua, phụ huynh… Phần này viết bằng PHP thuần, khá ổn định.

---

## 1. Từ điển: các khái niệm bạn sẽ gặp

| Thuật ngữ | Giải thích ngắn |
|---|---|
| **nRF52840** | Chip vi điều khiển của Nordic có Bluetooth. Board dùng ở đây là **SuperMini / ProMicro**. |
| **Firmware** | Chương trình chạy trên remote, viết bằng Arduino C++, file `.ino` + `.cpp`. Nạp bằng Arduino IDE. |
| **BLE** | Bluetooth Low Energy, Bluetooth tiết kiệm pin. |
| **BLE Advertising** | Cách cũ (V3.10): remote **la to** gói tin ra không khí, ai nghe được thì nghe. Không kết nối. Nhanh nhưng dễ rơi gói. |
| **BLE GATT** | Cách hiện tại (V3.11+): laptop **kết nối hẳn** với remote, gửi/nhận như nhắn tin riêng. Tin cậy hơn nhưng mỗi laptop chỉ phục vụ 1 remote. |
| **NUS** | Nordic UART Service, một "cổng nối tiếp ảo" qua GATT. Có 2 kênh: RX (laptop ghi vào) và TX (remote báo lên = *notify*). |
| **Central / Peripheral** | Laptop là *central* (chủ động kết nối), remote là *peripheral*. |
| **BlueZ / `hci0`** | Bộ Bluetooth của Linux / tên card Bluetooth của laptop. |
| **`bleak`** | Thư viện Python dùng để nói chuyện Bluetooth. |
| **MQTT** | Giao thức "đăng ký – phát tin". Chương trình A *publish* tin vào một *topic* (ví dụ `ars/1/resp`), chương trình B *subscribe* topic đó thì nhận được. |
| **Mosquitto** | Phần mềm trung chuyển MQTT (*broker*). |
| **Topic** | "Kênh" MQTT, dạng `ars/<room>/resp`, `ars/<room>/cmd/gw`… |
| **MariaDB** | Cơ sở dữ liệu (tương đương MySQL). Tên CSDL: `ars`. |
| **Migration** | File SQL `db/migrate_0XX_*.sql` nâng cấp cấu trúc CSDL theo thứ tự. |
| **systemd service** | Chương trình chạy nền tự khởi động cùng máy: `ars-ingest`, `ars-ble`… Xem bằng `systemctl status`, log bằng `journalctl`. |
| **Room** | Mã lớp 1–99. Remote nhớ room, lớp trên web có `room_id`. Hai số này **phải khớp**. |
| **Seat / ID** | Số ghế học sinh 1–99, học sinh tự gõ trên remote. |
| **Session (buổi học)** | Một lần giáo viên bấm "Bắt đầu" với một lớp và một bộ câu hỏi. Mỗi room chỉ có 1 buổi đang chạy. |
| **LOGIN** | Remote báo "tôi là ghế X" = điểm danh. |
| **ANSWER** | Remote gửi đáp án. |
| **seq** | Số thứ tự lần bấm (0–255). Gửi lại thì **giữ nguyên seq** để server biết là gói trùng. |
| **ACK / NACK** | Giấy báo nhận / báo từ chối, kèm mã lý do (`status`). |
| **STATE** | Server báo cho remote: câu nào đang chiếu, mở hay đóng, có mấy lựa chọn. |
| **`state_rev`** | Cột trong bảng `sessions`. Web tăng số này mỗi khi giáo viên thao tác, ingest thấy đổi thì phát STATE mới. |
| **HELLO** | Gói "còn sống không?" bridge gửi remote mỗi 2 giây, cũng dùng để hỏi room của remote. |

---

## 2. Bản đồ thư mục: đọc gì, bỏ qua gì

Ký hiệu: ⭐ quan trọng, đọc sớm · 📘 đọc khi cần · 💤 lịch sử / dữ liệu, có thể bỏ qua

```
ars-nrf52840-ble-main/
│
├── HUONG_DAN_NGUOI_MOI.md     ⭐ file này
├── TONG_HOP_DU_AN.md          ⭐ tổng hợp kỹ thuật (giao thức, bảng DB, danh sách file)
├── START_HERE_LETTER_ANSWERS.md ⭐ V3.14 (bản mới nhất)
├── START_HERE_AUTO_QUESTION.md  ⭐ V3.13
├── START_HERE_REMOTE_ROOM.md    ⭐ V3.12 (server hiện tại)
├── START_HERE_GATT.md           📘 V3.11, nền tảng GATT, có bảng xử lý sự cố
├── README.md                    📘 tổng quan web + giao thức Advertising CŨ (đọc cẩn thận, xem mục 5)
├── HUONG_DAN_CAI_DAT.md         📘 cài đặt chi tiết
├── UPGRADE_V10/V11/V12.md, CHANGES_V10.md  📘 lịch sử tính năng web
├── CURRENT_PROJECT_STATUS.md    📘 ghi chú trạng thái ngắn
├── config.ini.example           ⭐ mẫu cấu hình
│
├── firmware/                    ── CODE CHẠY TRÊN REMOTE ──
│   ├── ARS_remote_v3_14/        ⭐ BẢN ĐANG DÙNG
│   ├── ARS_remote_v3_13/        💤 dự phòng (đáp án hiện bằng số)
│   ├── ARS_remote_v3_11/        💤 dự phòng (chọn câu thủ công)
│   ├── ARS_remote_v3_10/        💤 bản Advertising cũ
│   └── PROTOCOL_V3_10.md, TEST_V3_10.md  💤 cho bản cũ
│
├── bridge/                      ── BLUETOOTH ⇄ MQTT ──
│   ├── ble_gatt.py              ⭐ bridge đang dùng (GATT)
│   ├── gatt_protocol.py         ⭐ đóng/mở khung byte, ghép kết quả với yêu cầu
│   ├── blecodec.py              📘 mã hoá/giải mã byte (dùng chung)
│   ├── ble_scan.py              💤 bridge Advertising cũ
│   └── bridge.py                💤 gateway USB tuỳ chọn
│
├── ingest/ingest.py             ⭐ "TRÁI TIM": kiểm tra gói, ghi DB, phát trạng thái
├── common/arscfg.py             ⭐ đọc config, kết nối DB, tạo client MQTT
│
├── db/                          ── CƠ SỞ DỮ LIỆU ──
│   ├── schema.sql               ⭐ bảng lõi
│   └── migrate_002 … 012        📘 nâng cấp theo thứ tự
│
├── web/                         ── WEBSITE (PHP) ──
│   ├── lib/bootstrap.php        ⭐ mọi trang đều nạp file này đầu tiên
│   ├── api/action.php           ⭐ lệnh của giáo viên (mở/đóng câu…)
│   ├── api/state.php            ⭐ dữ liệu bảng điều khiển (gọi mỗi giây)
│   ├── session.php              ⭐ trang bảng điều khiển buổi học
│   ├── *.php                    📘 các trang giáo viên khác
│   ├── student/  parent/        📘 cổng học sinh / phụ huynh
│   ├── lib/*.php                📘 nghiệp vụ: câu hỏi, AI, LMS, i18n…
│   ├── lang/en.php              📘 từ điển tiếng Anh
│   └── assets/                  📘 CSS/JS (control.js = JS bảng điều khiển); vendor/ = thư viện ngoài 💤
│
├── deploy/                      ── CÀI ĐẶT TRÊN UBUNTU ──
│   ├── install_ubuntu.sh        ⭐ cài toàn bộ
│   ├── install_gatt.sh          ⭐ BẮT BUỘC chạy thêm để dùng GATT (xem mục 8)
│   ├── upgrade_remote_room.sh   ⭐ cập nhật bridge V3.12
│   ├── rollback_*.sh            📘 quay lại bản trước
│   ├── ars                      ⭐ lệnh tiện ích `ars status`, `ars logs`…
│   └── *.service, *.conf        📘 cấu hình systemd / Apache / Mosquitto
│
├── tests/                       📘 kiểm thử tự động, *_RESULTS.md = kết quả đã chạy
├── tools/                       📘 sim_clickers.py (giả lập remote), công cụ dịch, báo cáo log
├── docs/                        📘 GATT_PROTOCOL_V3_11.md ⭐; Handover + BLUEZ = tài liệu thời Advertising
├── huong-dan-su-dung/           📘 hướng dẫn cho giáo viên / học sinh / phụ huynh / lập trình viên
├── history/                     💤 các bản ble_scan thử nghiệm cũ
├── bai-giang/, de-thi-test/, mau/  💤 dữ liệu mẫu (slide, đề thi để nhập thử)
```

**Kết luận:** để hiểu lõi hệ thống, bạn chỉ cần đọc kỹ **khoảng 6 file code**:
`firmware/ARS_remote_v3_14/ARS_remote_v3_14.ino`, `firmware/ARS_remote_v3_14/ars_ble.cpp`, `bridge/gatt_protocol.py`, `bridge/ble_gatt.py`, `ingest/ingest.py`, `web/api/action.php`.

---

## 3. Câu chuyện một lần bấm nút (đi qua từng file)

Tình huống: lớp **Room 1**, học sinh **ghế 2** trả lời **câu 5** bằng **đáp án C**.

### Bước 0: Chuẩn bị trên web
- Giáo viên tạo lớp với `room_id = 1`, thêm học sinh ghế 2 (`web/classes.php`, `web/class.php`).
- Bấm **Bắt đầu buổi học** → tạo dòng trong bảng `sessions` với `status = running`.

### Bước 1: Remote bật nguồn và kết nối
- `setup()` trong `ARS_remote_v3_14.ino`: test đèn, đọc room/ghế đã lưu trong flash (`loadIdentity`), bật Bluetooth (`ArsBle::begin`). Remote phát tên `ARS_REMOTE_01`.
- `ble_gatt.py` → hàm `run()` quét thấy remote → `Link.session()` kết nối → gửi **HELLO room=0** để hỏi "bạn đang ở room mấy?" → remote trả room 1 → `select_room(1)` đăng ký MQTT cho room 1 → log `GATT READY`.

### Bước 2: Điểm danh (LOGIN)
- Remote thấy kết nối sẵn sàng → `beginLogin()` gửi gói 9 byte `A5 01 01 02 00 seq 00 00 00`.
- Bridge nhận trong `on_notify()` → `Transactions.request()` gắn một **mã yêu cầu ngẫu nhiên** (`gatt_request`) → publish JSON lên `ars/1/resp`.
- `ingest.py` → `on_message()` → `process()` → `login()`: kiểm tra có buổi học, ghế 2 có trong lớp, máy này chưa đăng nhập ghế khác… → ghi bảng `session_logins` → `publish_gatt_result()` gửi kết quả lên `ars/1/result/gatt`.
- Bridge khớp mã yêu cầu + mọi trường → gửi `A5 14 …status=0` xuống remote → remote in `ACK LOGIN EXACT`, nháy xanh.

### Bước 3: Giáo viên mở câu 5
- Bấm "Mở câu" trên `session.php` → JavaScript `assets/control.js` gọi `api/action.php?action=open` → ghi `session_questions` (status `open`, hạn giờ) và `sessions.current_q` → `bump_state()` tăng `state_rev`.
- `ingest.state_loop()` (chạy mỗi 0,3 s) thấy `state_rev` đổi → `build_state()` → publish `STATE 1 5 1 4 …` (room 1, câu 5, đang mở, 4 lựa chọn).
- Bridge `on_mqtt()` mã hoá thành `A5 10 …` gửi xuống → remote `processDownlink()` cập nhật câu hiện tại → LED hiện `n` ↔ `05`.

### Bước 4: Học sinh chọn C rồi bấm OK
- `handleKey()`: phím C → `selectedAnswer = 3` → LED hiện chữ `C`.
- Phím OK → `beginAnswer()` → tạo giao dịch chờ (câu 5, seq mới, đáp án 3) → gửi `A5 02 01 02 05 seq 03 00 00` → LED hiện hai gạch chạy.

### Bước 5: Server kiểm tra và lưu
- Bridge → `ars/1/resp` → `ingest.answer()` kiểm tra lần lượt: đúng máy đã đăng nhập ghế 2? câu 5 thuộc buổi? có phải gói trùng? câu còn mở? còn trong hạn? C nằm trong 4 lựa chọn? có cho đổi đáp án không?
- Hợp lệ → `INSERT INTO responses` → log `NHẬN ghế 02 câu 5 … → C` → gửi kết quả `status=0`.
- Không hợp lệ → `reject()` ghi bảng `rejected` + gửi NACK với mã lý do (ví dụ `2 = QUESTION_CLOSED`).

### Bước 6: Remote nhận kết quả
- `finishAnswerAck()` chỉ chấp nhận khi **khớp cả câu, seq và đáp án**. Đúng → `ACK ANSWER EXACT`, đèn xanh. NACK → đèn đỏ, LED hiện `Er`.
- Không có kết quả sau 1 giây → `processRetry()` gửi lại **cùng seq** (tối đa 4 lần). Server thấy trùng thì không ghi lần hai, chỉ gửi lại ACK.

### Bước 7: Màn hình giáo viên cập nhật
- `control.js` và `projector.js` gọi `api/state.php` mỗi giây → ô ghế 2 đổi màu, biểu đồ tăng một phiếu C.

> 💡 **Mẹo:** mở 3 cửa sổ cùng lúc khi thử: Serial Monitor của remote, `journalctl -u ars-ble -u ars-ingest -f`, và trang bảng điều khiển. Bạn sẽ thấy đúng các bước trên chạy theo thứ tự.

---

## 4. Chạy thử lần đầu

### Cách A: Không cần phần cứng (nên làm trước)

Trên máy Ubuntu 22.04/24.04:

```bash
cd ars-nrf52840-ble-main
sudo bash deploy/install_ubuntu.sh   # cài Apache, PHP, MariaDB, Mosquitto, Python libs; chép code vào /opt/ars-server
ars status                           # các dịch vụ phải "active"
```

1. Mở `http://localhost/gv`, tạo tài khoản giáo viên đầu tiên (thành quản trị).
2. Tạo **lớp** với room = 1, thêm vài học sinh (ghế 1, 2, 3…). Có thể nhập từ Excel mẫu `mau/ARS_du_lieu_thu.xlsx`.
3. Tạo **bộ câu hỏi**: kéo thả `de-thi-test/Bai_giang_IOT/de_IOT.docx` (hoặc `.csv`) vào trang Soạn đề.
4. Vào lớp → **Bắt đầu buổi học** với bộ câu đó.
5. Trong terminal: `ars sim 10` (giả lập 10 remote ảo ở tầng MQTT, theo kiểu V3.10, ingest vẫn xử lý bình thường).
6. Trên bảng điều khiển bấm **Mở câu** → các ô ghế chuyển xanh dần.

Bạn đã thấy toàn bộ phần server + web hoạt động mà chưa cần Bluetooth.

### Cách B: Với remote thật

1. **Nạp firmware**: Arduino IDE → mở cả thư mục `firmware/ARS_remote_v3_14/` → chọn **đúng board/core SuperMini đã từng nạp thành công** (Adafruit nRF52) → Upload. Serial Monitor 115200 phải in `ARS Remote V3.14 GATT auto question / letter answers`.
2. **Chuyển server sang GATT** (bắt buộc, xem bẫy số 1 ở mục 8):
   ```bash
   sudo apt install python3-bleak python3-paho-mqtt python3-pymysql
   python3 bridge/ble_gatt.py --scan                 # ghi lại MAC của ARS_REMOTE_01
   sudo nano /opt/ars-server/config.ini              # mục [ble]: remote_address = <MAC>
   sudo bash deploy/install_gatt.sh
   sudo bash deploy/upgrade_remote_room.sh
   journalctl -u ars-ble -u ars-ingest -f
   ```
3. Trên remote: bấm **MODE** → gõ số ghế → **OK** (bấm MODE lần nữa để đổi sang nhập room).
4. Đợi log `GATT READY` rồi `ĐIỂM DANH ghế 02`. Mở câu trên web, chọn đáp án, bấm OK.

### Chạy kiểm thử tự động

```bash
bash tests/run_local.sh            # toàn bộ test web + ingest trên CSDL tạm, không đụng dữ liệu thật
bash tests/firmware_host/run.sh    # chạy code firmware thật trên máy tính với phần cứng giả lập
python3 tests/gatt_unit.py         # giao thức GATT
python3 tests/room_switch_unit.py  # chuyển phòng
```

---

## 5. Phiên bản: vì sao có nhiều thư mục firmware và tài liệu "mâu thuẫn"?

Dự án đã đi qua hai cách truyền Bluetooth:

```
V3.10  Advertising  ── uplink hay rơi gói (chỉ 55–94% tới server) ──┐
                                                                     ▼  đổi hướng
V3.11  GATT 1 remote  →  V3.12 room theo remote  →  V3.13 tự theo câu GV  →  V3.14 hiện chữ A/b/C/d  ← HIỆN TẠI
```

| Khi đọc… | Hãy nhớ |
|---|---|
| `README.md` mục 1–4 | Mô tả **Advertising V3.10** (beacon, `ble_scan.py`, Experimental=true). Phần web vẫn đúng. |
| `docs/ARS_BLE_Project_Handover.md` | Nhật ký debug thời Advertising, kế hoạch V3.10.6 **đã bị bỏ** khi chuyển GATT. Đọc để hiểu lý do. |
| `huong-dan-su-dung/lap-trinh-vien.md` | Quy ước web/DB/i18n vẫn đúng; phần Bluetooth/firmware đã cũ. |
| `START_HERE_*.md` | **Đúng cho bản hiện tại**; bản mới ghi đè bản cũ (3.14 > 3.13 > 3.12 > 3.11). |
| `firmware/ARS_remote_v3_14/README.md` | Tiêu đề vẫn ghi "V3.11" nhưng nội dung GATT vẫn đúng. |

Các thư mục firmware cũ được **giữ để quay lại khi cần**, không phải rác. Server V3.12 chạy được với cả firmware V3.11, V3.13 và V3.14. Nhưng firmware Advertising (V3.10) và server GATT **không nói chuyện được với nhau**.

---

## 6. Khi có lỗi: tìm ở đâu?

### Bước 1: Xem log theo thứ tự

| Thấy log | Nghĩa là đã đi tới đâu |
|---|---|
| Serial remote: `TX QUEUED` | Remote đã gửi |
| `journalctl`: `GATT RX` | Laptop đã nhận qua Bluetooth |
| `ĐIỂM DANH` / `NHẬN` / `TRÙNG` / `LOẠI <lý do>` | Ingest đã xử lý |
| `BACKEND RESULT` | Bridge đã có kết quả để gửi về |
| Serial remote: `ACK … EXACT` hoặc `NACK …` | Hoàn tất |

**Log dừng ở đâu thì lỗi nằm ngay sau đó.**

### Bước 2: Tra theo triệu chứng

| Triệu chứng | Kiểm tra |
|---|---|
| Remote nhấp nháy `bt` mãi | `systemctl status ars-ble`; dịch vụ có đang chạy `ble_gatt.py` không (`systemctl cat ars-ble`); MAC trong config; điện thoại nào đang chiếm kết nối? |
| `LG` / NACK `NO_SESSION` (4) | Lớp có `room_id` trùng room trên remote chưa? Có buổi học **đang chạy** không? |
| NACK `UNKNOWN_SEAT` (8) | Ghế gõ trên remote chưa có trong danh sách lớp |
| NACK `SEAT_TAKEN` (11) / `MAC_BOUND` (12) | Ghế đã có máy khác / máy này đã gắn ghế khác. Bấm vào ô ghế trên bảng điều khiển để **giải phóng** |
| NACK `NO_CHANGE` (7) | Đã trả lời câu này mà buổi không cho đổi đáp án. Đây là đúng luật, không phải lỗi |
| LED `CL` hoặc `--` | Câu đang chiếu đã đóng / chưa mở câu nào |
| Có `GATT RX`, không có `BACKEND RESULT` | `ars-ingest` có chạy không? đã cài ingest mới (`install_gatt.sh`) chưa? |
| Web không đổi màu | `ars logs`, xem bảng "Gói bị từ chối" trên bảng điều khiển, hoặc `ars watch` |
| Remote báo `ACK TIMEOUT` | Kết quả **chưa rõ**: xem web trước khi bấm lại |

Bảng đầy đủ mã lỗi: mục 5.2 của `TONG_HOP_DU_AN.md`.

### Lệnh hữu ích

```bash
ars status                 # tình trạng các dịch vụ
ars logs                   # log ingest + bluetooth
ars mqtt                   # xem mọi tin MQTT đang chạy qua
ars watch                  # xem CSDL trực tiếp
ars sql "SELECT * FROM rejected ORDER BY id DESC LIMIT 10"
ars restart
```

---

## 7. Sửa code lần đầu: công thức cho việc hay gặp

> Luôn hỏi trước: **luật này nên nằm ở đâu?** Gần như mọi luật đều nằm ở `ingest.py`.

| Muốn… | Sửa ở đâu | Lưu ý |
|---|---|---|
| Thêm/đổi luật chấp nhận đáp án | `ingest/ingest.py`, hàm `answer()` / `login()` | Lý do mới thì thêm vào `REJECT_STATUS` **và** `resultStatusName()` trong `.ino` để remote in đúng tên |
| Đổi hiển thị LED | `firmware/…/display.cpp` + `renderUi()` trong `.ino` | Chạy `tests/firmware_host/run.sh` trước khi nạp |
| Đổi thời gian chờ / số lần gửi lại | `ACK_LISTEN_MS`, `MAX_ATTEMPTS`, `BACKOFF_MS` trong `.ino` | Mỗi lần chỉ đổi **một nhóm thông số** rồi đo lại |
| Thêm lệnh giáo viên (nút trên bảng điều khiển) | `web/api/action.php` (thêm `case`) + `web/assets/control.js` | Kết thúc bằng `bump_state()` để remote biết |
| Thêm dữ liệu cho bảng điều khiển | `web/api/state.php` | File này được gọi mỗi giây: viết truy vấn nhẹ |
| Thêm trang web mới | Tạo `web/xxx.php`, mở đầu bằng `require __DIR__.'/lib/bootstrap.php'; require_login();`, dùng `page_head()` / `page_foot()` | Form POST phải có `csrf_field()` + `check_csrf()`; truy vấn dùng `q()/q1()/qall()` (PDO, có tham số) |
| Thêm cột/bảng | Tạo `db/migrate_013_….sql` (dùng `IF NOT EXISTS`) | Thêm vào `install_ubuntu.sh` và `tests/run_local.sh` |
| Thêm bản dịch tiếng Anh | Bọc chuỗi bằng `t('…')`, thêm khoá vào `web/lang/en.php` | Công cụ: `python3 tools/i18n_wrap.py keys web` |

### Đưa code đã sửa lên máy chạy thật

```bash
sudo rsync -a --exclude config.ini --exclude .git --exclude __pycache__ ./ /opt/ars-server/
sudo systemctl restart apache2 ars-ingest ars-ble
```

> ⚠️ Đừng dùng `rsync --delete` lên máy đã cài GATT mà không xem trước: thư mục `/opt/ars-server/backups/` (chứa bản sao lưu do script tạo) có thể bị xoá.

---

## 8. Những cái bẫy cần tránh

1. **Cài mới xong mà remote không kết nối.** File `deploy/ars-ble.service` vẫn chạy `ble_scan.py` (cách cũ). Đường GATT chỉ bật khi chạy `deploy/install_gatt.sh`: script này tạo file ghi đè `/etc/systemd/system/ars-ble.service.d/gatt.conf`. Kiểm tra bằng `systemctl cat ars-ble`.
2. **Room phải khớp 3 nơi** (từ V3.12 chỉ còn 2): room trên remote = `room_id` của lớp trên web. Room chỉ dùng **1–99** (tài liệu cũ ghi 0–255 là sai với GATT).
3. **Chỉ 1 remote một lúc** trong chế độ GATT (tên cố định `ARS_REMOTE_01`, laptop kết nối 1 thiết bị). Nhiều remote cần thiết kế lại.
4. **Không có ACK không có nghĩa là chưa lưu.** Mất kết nối đúng lúc chờ: DB có thể đã ghi. Xem web trước.
5. **Không sửa `config.ini` bằng cách chép đè từ `config.ini.example`**: sẽ mất mật khẩu DB thật. Chỉ sửa từng dòng.
6. **Không đưa `config.ini` lên Git** (đã có trong `.gitignore`).
7. **Không dùng `sudo ars ble` để thử GATT**: lệnh đó chỉ nghe gói Advertising.
8. **Không nạp bootloader / xoá toàn bộ flash** khi nạp firmware: mất room/ghế đã lưu, có thể làm hỏng board.
9. **Pin luôn = 0**: firmware chưa đo pin, cảnh báo pin yếu trên web sẽ không có tác dụng.
10. **Không có mã hoá Bluetooth**: chấp nhận được cho demo, cần làm riêng nếu triển khai thật.
11. **Đổi nhiều thông số radio cùng lúc** thì không biết cái nào có tác dụng. Mỗi lần đổi một thứ, đo 20–30 lần bấm.

---

## 9. Hỏi đáp nhanh

**Hỏi: Tôi chỉ làm web, có cần hiểu Bluetooth không?**
Không. Web chỉ đọc/ghi CSDL. Nhớ một điều: thay đổi nào ảnh hưởng remote thì gọi `bump_state($session_id)`.

**Hỏi: Remote biết câu nào đang mở bằng cách nào?**
Ingest phát STATE (câu đang chiếu + mở/đóng + số lựa chọn) mỗi khi `state_rev` đổi và định kỳ 5 giây. Từ V3.13, remote tự hiện câu đó. Phím trái/phải không còn đổi câu.

**Hỏi: Vì sao gửi lại phải giữ nguyên seq?**
Để server nhận ra đây là cùng một lần bấm (trùng trong 10 giây), không ghi hai lần mà chỉ gửi lại ACK.

**Hỏi: `responses` và `final_answers` khác nhau thế nào?**
`responses` lưu **mọi** lần bấm hợp lệ (kể cả đổi đáp án). `final_answers` là VIEW lấy **lần cuối** của mỗi ghế cho mỗi câu, dùng để chấm điểm.

**Hỏi: Muốn thử mà không có remote?**
`ars sim 10` hoặc `python3 tools/sim_clickers.py --room 1 -n 10` (thêm `--loss 0.3` để giả lập rơi gói, `--bad` để thêm gói sai).

**Hỏi: Trợ lý AI cần gì?**
Vào Cài đặt chọn nhà cung cấp (`offline` không cần mạng; Claude / OpenAI-tương thích / Gemini cần API key). Code ở `web/lib/ai.php`, trợ lý học sinh ở `web/lib/tutor.php`.

**Hỏi: Chạy trên Windows được không?**
Phần web + ingest được (XAMPP + Mosquitto + Python). Nhưng nên dùng Ubuntu vì toàn bộ script triển khai và Bluetooth được viết cho Linux/BlueZ.

---

## 10. Việc nên làm trong tuần đầu

- [ ] Đọc file này + `TONG_HOP_DU_AN.md`.
- [ ] Cài theo **Cách A** (mục 4), chạy `ars sim`, thao tác hết một buổi học trên web: mở câu, đóng câu, xem kết quả, xuất Excel.
- [ ] Chạy `bash tests/run_local.sh` và 3 bộ test firmware/GATT, đảm bảo đều đạt.
- [ ] Đọc `ingest/ingest.py` từ `process()` trở xuống, đối chiếu với mục 3 ở trên.
- [ ] Đọc `firmware/ARS_remote_v3_14/ARS_remote_v3_14.ino` từ `loop()` ngược lên.
- [ ] Đọc `bridge/gatt_protocol.py` rồi `bridge/ble_gatt.py`.
- [ ] Nạp firmware V3.14 vào remote thật, làm **Cách B**, thử 20 lần bấm, ghi lại số ACK / NACK / TIMEOUT.
- [ ] Thử một thay đổi nhỏ (ví dụ thêm một dòng log trong `ingest.answer()`), triển khai lên `/opt/ars-server`, xem log.
- [ ] Ghi lại những gì bạn thấy khó hiểu vào cuối file này để người sau đỡ vất vả hơn.

---

*Tài liệu liên quan: [`TONG_HOP_DU_AN.md`](TONG_HOP_DU_AN.md) (tra cứu kỹ thuật) · [`START_HERE_LETTER_ANSWERS.md`](phien-ban/START_HERE_LETTER_ANSWERS.md) · [`docs/GATT_PROTOCOL_V3_11.md`](GATT_PROTOCOL_V3_11.md) · [`huong-dan-su-dung/`](huong-dan-su-dung/README.md)*
