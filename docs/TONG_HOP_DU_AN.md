# TỔNG HỢP DỰ ÁN ARS (nRF52840 ↔ Laptop) — đọc để hiểu code & dự án

> File tổng hợp được viết sau khi đọc toàn bộ tài liệu và các file code chính của repo.
> Mục tiêu: một người mới đọc file này là nắm được dự án làm gì, chạy thế nào, code nằm đâu,
> phiên bản nào đang "thật sự" chạy, và chỗ nào tài liệu đã cũ.

---

## 1. Dự án là gì?

**ARS (Audience/Classroom Response System)** — hệ thống bấm trả lời trắc nghiệm trong lớp:

- Mỗi học sinh có một **Remote tự chế** dùng chip **nRF52840** (board SuperMini/ProMicro) với bàn phím 4×4, LED 7 đoạn 2 số và LED trạng thái đỏ/xanh.
- **Laptop Ubuntu của giáo viên** là server: nhận đáp án qua **Bluetooth Low Energy tích hợp** (không cần gateway), kiểm tra hợp lệ, lưu vào **MariaDB**, hiển thị trên **web PHP** (bảng điều khiển GV, màn chiếu, cổng học sinh, cổng phụ huynh).
- Ngoài phần "bấm remote", web còn là một **LMS nhỏ**: ngân hàng câu hỏi, soạn đề từ Word/Excel/PDF, bài giảng, bài tập về nhà, trợ lý AI, thi đua đổi quà, Zalo/SMS phụ huynh, đồng bộ Cloud, đa ngôn ngữ VI/EN, đăng nhập Google/Facebook.

**Nguyên tắc thiết kế (không được phá):**

1. **Remote và bộ thu không quyết định gì** — mọi luật (trùng gói, sai ghế, câu đóng, trễ giờ…) nằm ở `ingest/ingest.py`.
2. **Web không nói MQTT** — PHP chỉ ghi DB rồi tăng `sessions.state_rev`; ingest thấy đổi sẽ phát trạng thái xuống Remote (≤ 0,3 s).
3. **Chạy offline được** — mọi thứ trên 1 laptop; chỉ AI / OAuth / Zalo-SMS / Cloud / Google Dịch cần mạng.
4. **Thời gian lấy theo đồng hồ MariaDB** (`NOW(3)`) để web và ingest không lệch nhau.

---

## 2. Lịch sử phiên bản — CÁI NÀO ĐANG DÙNG?

Đây là điểm dễ nhầm nhất: repo chứa **hai đường truyền khác nhau** và tài liệu của cả hai.

| Phiên bản | Đường truyền | Thay đổi chính | Trạng thái |
|---|---|---|---|
| V3.10 (+ 3.10.4/5/6 thử nghiệm) | **BLE Advertising** (quảng bá, không kết nối) — `bridge/ble_scan.py` | Remote phát gói 150 ms, laptop phát beacon ACK/STATE. Cần `Experimental = true` trong BlueZ. | **Cũ** – giữ để rollback. Vấn đề: uplink hay bị miss (chỉ 55–94 % gói tới server). |
| **V3.11** | **BLE GATT** (kết nối, Nordic UART Service) — `bridge/ble_gatt.py` + `bridge/gatt_protocol.py` | Kết nối 1 remote, ACK/NACK chính xác cho cả LOGIN và ANSWER qua MQTT `result/gatt`. | Nền tảng hiện tại |
| **V3.12** | GATT | Room lấy **từ remote** (HELLO 0 để dò), đổi room không cần sửa config/không ngắt BLE. Chỉ đổi `ble_gatt.py`. | **Server hiện tại** |
| **V3.13** | GATT | Firmware **tự theo câu GV đang chiếu** (STATE), khoá chọn khi câu đóng; LEFT/RIGHT không còn đổi câu. | Firmware cũ hơn 1 bậc |
| **V3.14** | GATT | Firmware hiển thị đáp án **bằng chữ** (A b C d E F G H I J) thay vì số. Chỉ khác `display.cpp` + `.ino`. | **Firmware hiện tại** |

👉 **Cấu hình đang dùng = firmware `firmware/ARS_remote_v3_14/` + server bridge V3.12 (`bridge/ble_gatt.py`) + `ingest/ingest.py`.**

Thứ tự đọc tài liệu chính thức: `START_HERE_LETTER_ANSWERS.md` (V3.14) → `START_HERE_AUTO_QUESTION.md` (V3.13) → `START_HERE_REMOTE_ROOM.md` (V3.12) → `START_HERE_GATT.md` (V3.11) → `docs/GATT_PROTOCOL_V3_11.md`.
Phần lớn `README.md` (mục 3–4) và `docs/ARS_BLE_Project_Handover.md` mô tả **đường Advertising cũ**.

---

## 3. Kiến trúc tổng thể (đường GATT hiện tại)

```
 ┌──────────────────┐  BLE GATT (NUS)   ┌────────────────────┐   MQTT    ┌──────────────┐  SQL  ┌─────────┐
 │ Remote nRF52840  │ ── Notify (TX) ──▶│ bridge/ble_gatt.py │ ────────▶│ ingest.py    │──────▶│ MariaDB │
 │ firmware V3.14   │ ◀── Write (RX) ── │ dịch vụ ars-ble     │ ◀──────── │ dịch vụ      │◀──────│  `ars`  │
 │ (peripheral)     │                   │ (central, bleak)    │           │ ars-ingest   │       └────▲────┘
 └──────────────────┘                   └────────────────────┘           └──────────────┘            │
                                                                                               ┌──────┴──────┐
                                                                                               │ web/ PHP    │◀── GV, màn chiếu,
                                                                                               │ Apache      │    HS, phụ huynh
                                                                                               └─────────────┘
```

Các dịch vụ systemd trên laptop: `apache2`, `mariadb`, `mosquitto`, `bluetooth`, `ars-ingest`, `ars-ble`, `ars-mdns` (`ars-bridge` = gateway USB tuỳ chọn, mặc định tắt).

---

## 4. Firmware Remote (`firmware/ARS_remote_v3_14/`)

Arduino + **Adafruit nRF52 core 1.7.0** (Bluefruit). Build thử trên target Feather nRF52840 (Flash ~138 KB, RAM ~15 KB) nhưng **nạp bằng profile SuperMini đã chạy được**.

| File | Vai trò |
|---|---|
| `ARS_remote_v3_14.ino` (~610 dòng) | Logic chính: máy trạng thái UI, LOGIN/ANSWER, retry, lưu Room/Seat vào flash, xử lý STATE |
| `ars_ble.cpp/.h` | Lớp BLE: NUS service, đóng/mở khung `[len, A5 …]`, HELLO, PING/PONG, giải mã kết quả |
| `keypad.cpp/.h` | Quét ma trận 4×4, phát sự kiện phím (`KEY_1_A…KEY_0_J, LEFT, RIGHT, MODE, OK, MULTI`) |
| `display.cpp/.h` | Quét LED 7 đoạn 2 số (common anode, digit qua PNP 2N3906, active LOW), các mode hiển thị |
| `status_led.cpp/.h` | LED đỏ/xanh, nháy có thời hạn |
| `board_pins.h` | Map GPIO thật của PCB |

### 4.1 Phần cứng

```
EXT_VCC P0.13 | SEG A..G: P0.06 P0.08 P0.17 P0.20 P0.22 P0.24 P1.00 | DIG1 P0.11 DIG2 P1.04 | STATUS P1.06
ROW1..4: P1.13 P1.11 P0.10 P0.09 | COL1..4: P0.31 P0.29 P0.02 P1.15
Phím: S1=A S2=B S3=LEFT S4=C | S5=D S6=E S7=RIGHT S8=F | S9=G S10=H S11=MODE S12=I | S13=J S14=OK
```

### 4.2 Luồng hoạt động trong `loop()`

```
ArsBle::update()      → đọc byte UART, ghép khung, sinh sự kiện (login/answer result, STATE, OPENMASK)
processConnection()   → phát hiện BLE ready/lost; lost ⇒ huỷ giao dịch đang chờ (kết quả UNKNOWN), bắt LOGIN lại
processDownlink()     → khớp ACK LOGIN/ANSWER; cập nhật câu hiện tại từ STATE
processRetry()        → chưa có kết quả sau 1000 ms ⇒ backoff 80–120 ms ⇒ gửi lại CÙNG seq (tối đa 4 lần)
handleKey()           → MODE nhập ghế/phòng, A–J chọn, OK gửi
renderUi() / displayUpdate() / statusLedUpdate()
```

Điểm quan trọng:
- **Định danh Room/Seat** lưu trong `/ars_id.bin` (InternalFS) dạng `A5 room seat xor`. Room và Seat nhập 1–99.
- `seq` 8 bit, khởi tạo ngẫu nhiên khi boot; retry giữ nguyên seq để server khử trùng.
- Giao dịch đang chờ **bất biến**: GV đổi câu giữa chừng không làm đổi câu/seq/đáp án của gói đang chờ.
- Chỉ chấp nhận ACK khi **khớp đúng câu + seq + đáp án**; STATE/ATTEND không bao giờ được coi là ACK.
- Mất kết nối ⇒ **không tự gửi lại** đáp án cũ (tránh ghi đáp án trễ sai thời điểm).
- Pin: `TEST_BATTERY_MV = 0` (chưa đo ADC — TODO).
- Tên quảng bá cố định `ARS_REMOTE_01`, chỉ 1 central kết nối ⇒ **thiết kế cho 1 remote**.

### 4.3 Màn hình LED

| Hiển thị | Ý nghĩa |
|---|---|
| `n` ↔ `05` | Câu 05 đang mở, chọn được |
| `A`/`b`/`C`/`d`… cố định | Đã chọn đáp án (V3.14), chưa gửi |
| hai gạch chạy | Đang chờ kết quả LOGIN/ANSWER |
| `CL` | Câu hiện tại đã đóng |
| `--` | Chưa có STATE hợp lệ |
| `r` ↔ số / `Id` ↔ số | Đang nhập Room / Seat |
| `bt` nhấp nháy | Chưa kết nối bridge |
| `LG` | Kết nối rồi nhưng chưa LOGIN được |
| `Er` + đỏ ~1,8 s | Bị từ chối / timeout / không hợp lệ |

---

## 5. Giao thức

### 5.1 BLE GATT (NUS) — `docs/GATT_PROTOCOL_V3_11.md`, `bridge/gatt_protocol.py`

- Service `6e400001-…`, RX `6e400002-…` (laptop **write** có response), TX `6e400003-…` (remote **notify**).
- Mỗi bản ghi: `[length, payload…]`, payload bắt đầu `A5`, tổng ≤ 20 byte ATT.

| Payload | Chiều | Ý nghĩa |
|---|---|---|
| `A5 20 room` | laptop→remote | HELLO mỗi 2 s (room=0: chỉ dò room) |
| `A5 21 room seat` | remote→laptop | Trả lời HELLO |
| `A5 22/23 token[4]` | hai chiều | PING/PONG đo trễ (`--probe`) |
| `A5 type room seat q seq ans battLo battHi` | remote→laptop | Uplink 9 byte: type 1=LOGIN, 2=ANSWER; ans 1..10=A..J |
| `A5 14 room seat seq status` | laptop→remote | Kết quả LOGIN chính xác |
| `A5 13 room 01 seat q seq ans status` | laptop→remote | Kết quả ANSWER chính xác |
| `A5 10 room q open nOpt bitmap[13]` | laptop→remote | STATE (câu đang chiếu) |
| `A5 12 room mask[8]` | laptop→remote | OPENMASK (câu nào đang mở) |

### 5.2 Mã trạng thái (status) — dùng chung ingest & firmware

`0 OK · 1 BAD_OPTION · 2 QUESTION_CLOSED · 3 NOT_LOGGED_IN · 4 NO_SESSION · 5 QUESTION_NOT_OPEN · 6 LATE · 7 NO_CHANGE · 8 UNKNOWN_SEAT · 9 MAPPING_MISMATCH · 10 ID_MISMATCH · 11 SEAT_TAKEN · 12 MAC_BOUND · 13 WRONG_LINK · 14 MALFORMED · 255 khác`

### 5.3 MQTT nội bộ (Mosquitto, 1883 chỉ localhost)

| Topic | Chiều | Nội dung |
|---|---|---|
| `ars/<room>/resp` | bridge → ingest | JSON gói: `mac, room, type, id, q, seq, ans, batt, rssi, via=ble, transport=gatt, gatt_request (token 32 hex), ts` |
| `ars/<room>/result/gatt` | ingest → bridge | Kết quả chính xác (không retain) kèm `gatt_request` + `status` |
| `ars/<room>/cmd/gw` | ingest → bridge | Lệnh text `STATE … / ATTEND … / OPENMASK … / ACKS …` |
| `ars/<room>/state` | ingest → mọi bên (retain) | JSON trạng thái đầy đủ + `cmds[]` |
| `ars/<room>/live` | ingest → | Số đã trả lời, phân bố đáp án |
| `ars/<room>/gw/status` | bridge → ingest (retain, LWT) | `online, port, pkt_per_s` |

Bridge GATT chỉ chuyển **STATE** và **OPENMASK** xuống remote; kết quả chỉ lấy từ `result/gatt` và phải **khớp token + mọi trường** (`Transactions.result`).

### 5.4 Giao thức Advertising cũ (V3.10, tham khảo)

Manufacturer Data company `0xFFFF`, cùng 9 byte uplink; downlink là 4 beacon `A5 10 STATE`, `A5 11 ATTEND`, `A5 12 OPENMASK`, `A5 13 ACKS (≤4 bản ghi)`. Chi tiết: `firmware/PROTOCOL_V3_10.md`, `bridge/blecodec.py`, `bridge/ble_scan.py`.

---

## 6. Luồng nghiệp vụ end-to-end

### 6.1 Kết nối & LOGIN
1. `ble_gatt.py` quét tìm remote theo `remote_address` hoặc tên `ARS_REMOTE_01` + service NUS (nhiều remote trùng ⇒ báo lỗi, bắt khai MAC).
2. Kết nối, bật Notify, gửi **HELLO 0** → remote trả room đã lưu → bridge mở MQTT cho room đó (`select_room`) → HELLO đúng room → `GATT READY`.
3. Remote thấy ready → gửi LOGIN (q=0). Bridge gắn token → `ars/<room>/resp`.
4. `ingest.login()`: kiểm buổi đang chạy, ghế có trong lớp, ghép MAC↔ghế (`device_mappings`), ghế/MAC đã login chưa → `INSERT session_logins` → publish kết quả → bridge viết `A5 14 …` → remote `ACK LOGIN EXACT`.

### 6.2 GV mở câu
`session.php` → `api/action.php` (`open/close/next/current/end/release/allow_change/show_result`) ghi `session_questions` và `sessions.current_q` → `bump_state()` tăng `state_rev` → `ingest.state_loop` (chu kỳ 0,3 s) phát STATE/OPENMASK → remote hiện `n ↔ số câu`. Ingest cũng **tự đóng câu hết giờ** và phát lại STATE định kỳ 5 s.

### 6.3 ANSWER — thứ tự kiểm tra trong `ingest.process()/answer()`
1. Định dạng (`malformed`) → 2. Ghi `devices` (pin, RSSI, last_seen) → 3. Có buổi đang chạy cho room (`no_session`) → 4. `via` phải là `ble` (`wrong_link`) → 5. Ghép MAC cố định (`mapping_mismatch`) → 6. Đã login & đúng ghế (`not_logged_in`/`id_mismatch`) → 7. Câu thuộc buổi (`q_not_open`) → 8. **Trùng** (cùng câu+MAC+seq+đáp án trong 10 s) ⇒ trả lại ACK, đếm `pkt_dup` → 9. Câu còn mở / chưa trễ (`q_closed`/`late`) → 10. Đáp án trong số lựa chọn (`bad_option`) → 11. Không cho đổi đáp án mà đã trả lời (`no_change`) → **INSERT `responses`** → ACK.

Bị loại ⇒ ghi bảng `rejected` (gộp bản lặp trong 10 s) + NACK có status.

### 6.4 Hiển thị
`control.js` / `projector.js` gọi `api/state.php` mỗi giây → lưới ghế, đồng hồ, biểu đồ phân bố (`final_answers` VIEW = đáp án cuối mỗi ghế).

---

## 7. Cơ sở dữ liệu (`db/`)

Chạy `schema.sql` rồi lần lượt `migrate_002` → `012`.

| Nhóm | Bảng |
|---|---|
| Lõi ARS (`schema.sql`) | `teachers, classes (room_id), students (seat_no), devices, question_sets, questions, sessions (state_rev, current_q, allow_change), session_questions, session_logins, responses, rejected, gateways`, VIEW `final_answers` |
| 002 Học sinh | `student_users, practice_assignments, practice_attempts, practice_items, wrong_notes` |
| 003 Bài giảng/AI | `lessons, settings, ai_log, tutor_messages, tutor_answers` |
| 004 | GV admin/khoá, `classes.conn_mode` |
| 005 LMS | `schools, question_media, device_mappings, homework*, parents, parent_links, parent_invites, teacher_comments` |
| 006 | `school_cohorts, sync_log/tokens/map, rewards, reward_redemptions, student_profiles, notifications` |
| 007 | `oauth_identities` |
| 008–011 | HS tự đăng ký, ngôn ngữ, `tutor_conversations`, trạng thái hoàn tất bộ đề |
| 012 | Ép mọi lớp dùng Bluetooth (nRF only) |

---

## 8. Web PHP (`web/`) — không framework

- `lib/bootstrap.php`: nạp đầu mọi trang — `cfg()`, PDO `db()/q()/q1()/qall()/qv()`, phiên, CSRF, `own_class/own_set/own_session` (kiểm quyền sở hữu), `bump_state()`, `page_head()/page_foot()`, link chia sẻ/QR.
- **Giáo viên**: `dashboard, classes, class, session (bảng điều khiển), projector, sessions, results, export, devices, mapping, sets, set, compose, media, library, variants, set_export/docx/print, lessons, lesson, homework, homework_grade, analytics, cohort, family, rewards, school(s), teachers, sync, notify, settings`.
- **API JSON** `web/api/`: `state.php`, `action.php`, `qparse.php`, `qadd.php`, `ai.php`, `sync.php` (Cloud nhận dữ liệu).
- **Học sinh** `web/student/`: home, quiz/practice/review, wrong/right (sổ câu sai/đúng), lectures, homework, tutor (AI "Cú Học"), rewards, register…
- **Phụ huynh** `web/parent/`: đăng nhập bằng mã mời, xem tiến độ con.
- **Thư viện nghiệp vụ** `web/lib/`: `qparse/extract` (tách câu từ DOCX/XLSX/PDF/PPTX), `qbank`, `sheet` (đọc/ghi xlsx không thư viện), `stats`, `variants`, `lms`, `rewards`, `sync`, `notify` (Zalo/SMS), `oauth`, `ai` (offline / Claude / OpenAI-compatible / Gemini), `tutor`, `i18n` (`t()/te()`, từ điển `lang/en.php`).
- **JS** `web/assets/`: `control.js`, `projector.js`, `compose.js`, `qeditor.js`, `tutor.js`, `gateway.js` (Web Serial), `i18n.js`, vendor KaTeX/mqtt.js/qrcode.

Link tắt: `/gv` (giáo viên), `/hs` (học sinh), `/ars/parent/`.

---

## 9. Triển khai & vận hành (`deploy/`)

| File | Vai trò |
|---|---|
| `install_ubuntu.sh` | Cài một lệnh: Apache+PHP, MariaDB, Mosquitto, Python libs → `/opt/ars-server` |
| `install_gatt.sh` / `rollback_gatt.sh` | Chuyển `ars-ble` sang `ble_gatt.py` (drop-in `/etc/systemd/system/ars-ble.service.d/gatt.conf`), cập nhật ingest, có backup |
| `upgrade_remote_room.sh` / `rollback_remote_room.sh` | Cập nhật bridge V3.12 (có backup tar.gz) |
| `ars` | Lệnh tiện ích: `status, logs, restart, ble, gateway ble/usb, sim, links, public on/off, mqtt, db, sql, tables, watch, gv, reset-gv, backup…` |
| `*.service` | `ars-ingest`, `ars-ble`, `ars-bridge`, `ars-mdns` |
| `apache-ars.conf`, `mosquitto-ars.conf` | Alias `/ars`, chặn `lib/`, proxy WebSocket `/mqtt`; listener 1883 + 9001 |

Cấu hình: `/opt/ars-server/config.ini` (mẫu `config.ini.example`): `[db] [mqtt] [gateway] [ble] [ingest] [storage]`. Với GATT quan trọng nhất là `[ble] remote_address` và `remote_name`.

Log debug GATT: `journalctl -u ars-ble -u ars-ingest -f`. Mốc: `GATT READY` → `GATT RX` → `ĐIỂM DANH`/`NHẬN`/`TRÙNG`/`LOẠI` → `BACKEND RESULT` → Serial remote `ACK … EXACT` + `RESULT elapsed_ms=`.

---

## 10. Kiểm thử & công cụ

- `bash tests/run_local.sh` — dựng MariaDB + PHP tạm trong /tmp, chạy toàn bộ test, không đụng DB thật.
- Firmware host test: `bash tests/firmware_host/run.sh` (chạy code `.ino` thật với stub Arduino/Bluefruit).
- Python: `tests/gatt_unit.py` (19 test giao thức/backend), `tests/room_switch_unit.py` (10 test chuyển phòng), `ble_scan_unit.py`, các `*_integration.py` (ingest, LMS, OAuth, i18n, tutor, Cloud…), `http_smoke.py`, `ui_smoke.cjs` (Playwright).
- Kết quả đã ghi: `tests/GATT_RESULTS.md`, `REMOTE_ROOM_RESULTS.md`, `AUTO_QUESTION_RESULTS.md`, `LETTER_ANSWERS_RESULTS.md`.
- `tools/sim_clickers.py` (giả lập N remote ở tầng MQTT, `ars sim`), `tools/ble_txn_report.py` (phân loại UPLINK_MISS/ACK_MISS từ log), `tools/i18n_*.py`.
- Dữ liệu mẫu: `bai-giang/` (slide 5 môn), `de-thi-test/` (5 bộ đề 20 câu, CSV/XLSX/DOCX, sinh bởi `tao_de.py`), `mau/`.
- `history/server_bridge/` — các bản `ble_scan.py` V3.10.4/5/6 thử nghiệm Advertising.

> Lưu ý: tất cả kiểm thử V3.11–V3.14 là **host/unit/compile**; tài liệu ghi rõ **chưa thử trên PCB/Bluetooth thật** cho V3.12–V3.14.

---

## 11. Những điểm cần chú ý / chỗ tài liệu chưa đồng bộ (nhận xét khi đọc code)

1. **`deploy/ars-ble.service` vẫn chạy `ble_scan.py`** (Advertising). Đường GATT chỉ có hiệu lực nhờ drop-in do `install_gatt.sh` tạo. Cài mới bằng `install_ubuntu.sh` mà quên `install_gatt.sh` ⇒ server chạy giao thức cũ, không nói chuyện được với firmware V3.11+.
2. **Tài liệu cũ chưa cập nhật**: `README.md` mục 1–4, `huong-dan-su-dung/lap-trinh-vien.md` (vẫn nói firmware V3.10, `ble_scan.py`), `docs/ARS_BLE_Project_Handover.md` (định hướng V3.10.6 — đã bị thay bằng GATT). `firmware/ARS_remote_v3_14/README.md` vẫn có tiêu đề "V3.11".
3. **Phạm vi Room không thống nhất**: README nói room 0–255; firmware cho nhập 1–99; `ingest.publish_gatt_result` và `ble_gatt.py` chỉ chấp nhận 1–99. Lớp trên web có `room_id` > 99 sẽ không dùng được với GATT.
4. **Chỉ 1 remote** ở chế độ GATT (tên cố định, một kết nối, bridge từ chối khi có nhiều thiết bị trùng). Mở rộng nhiều remote cần thiết kế lại bridge (nhiều kết nối) hoặc quay lại Advertising.
5. **Chưa đo pin** (batt = 0), cảnh báo pin yếu trên web sẽ không có tác dụng.
6. **Không pairing/mã hoá BLE** — tài liệu tự ghi nhận là việc bảo mật riêng.
7. Kết quả khi mất kết nối đúng lúc chờ ACK là **UNKNOWN**: DB có thể đã ghi; phải xem web trước khi bấm lại.
8. Dedup backend chỉ trong cửa sổ 10 s (seq 8 bit quay vòng) — không phải exactly-once tuyệt đối.
9. BlueZ: `Experimental = true` bắt buộc cho đường Advertising (`docs/BLUEZ_REQUIRED_CONFIG.md`), không bắt buộc cho GATT nhưng nên giữ để rollback được.

---

## 12. Lộ trình đọc code gợi ý

1. File này → `START_HERE_LETTER_ANSWERS.md` → `START_HERE_AUTO_QUESTION.md` → `START_HERE_REMOTE_ROOM.md`.
2. `docs/GATT_PROTOCOL_V3_11.md` + `bridge/gatt_protocol.py` (ngắn, nắm khung byte).
3. `firmware/ARS_remote_v3_14/ars_ble.cpp` → `ARS_remote_v3_14.ino` (đọc từ `loop()` ngược lên).
4. `bridge/ble_gatt.py` (lớp `Link`: `session` → `select_room` → `on_notify` / `on_mqtt` / `heartbeat`).
5. `ingest/ingest.py` (`process` → `login` / `answer` → `publish_gatt_result`; `state_loop` → `build_state`).
6. `db/schema.sql` → `web/lib/bootstrap.php` → `web/api/action.php` + `web/api/state.php` → `web/session.php` + `assets/control.js`.
7. Các tính năng LMS/AI trong `web/lib/*` khi cần.

## 13. Lệnh hay dùng

```bash
# Server
ars status ; ars logs ; ars restart
journalctl -u ars-ble -u ars-ingest -f
python3 bridge/ble_gatt.py --scan                       # tìm remote
python3 bridge/ble_gatt.py --address AA:BB:.. --probe 100  # đo PING/PONG
sudo bash deploy/install_gatt.sh                        # chuyển sang GATT
sudo bash deploy/upgrade_remote_room.sh                 # bridge V3.12
ars sim 30                                              # giả lập không cần phần cứng

# Test
bash tests/run_local.sh
bash tests/firmware_host/run.sh
python3 tests/gatt_unit.py ; python3 tests/room_switch_unit.py
```

Firmware: Arduino IDE mở cả thư mục `firmware/ARS_remote_v3_14/`, giữ đúng board/core SuperMini, Serial 115200 phải in `ARS Remote V3.14 GATT auto question / letter answers`.
