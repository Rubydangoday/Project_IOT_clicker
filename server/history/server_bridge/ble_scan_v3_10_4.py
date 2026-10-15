#!/usr/bin/env python3
"""ble_scan.py — dùng Bluetooth của laptop thay cho gateway USB: Remote nRF52840 ⇄ laptop ⇄ MQTT. Không có logic nghiệp vụ.

Chiều lên:  quét gói quảng bá BLE, lọc Manufacturer Data mã công ty [ble] company_id + byte 0xA5 (định dạng: bridge/blecodec.py)
            → JSON giống gateway USB → MQTT  ars/<room>/resp   (QoS 1, "via":"ble")
Chiều xuống: MQTT  ars/<ROOM>/cmd/gw  và bản giữ lại  ars/<ROOM>/state  → STATE / ATTEND / OPENMASK / ACKS.
            V3.10.4 giữ scan liên tục và dùng ACK/ATTEND burst dài nhưng có giới hạn; background beacon bị hoãn khi exact ACK còn pending.
            BlueZ chỉ dùng trên Linux; Windows/macOS hiện chỉ nghe, Remote không nhận được trạng thái.
Trạng thái:  ars/<ROOM>/gw/status  = {"online": true, "port": "bluetooth hci0", "pkt_per_s": ...}  (Last Will = offline)

Cần: python3-bleak (Ubuntu: sudo apt install python3-bleak; Windows: pip install bleak), Bluetooth của laptop đang bật.
Chạy:  python3 bridge/ble_scan.py            (room, adapter lấy trong config.ini)
       python3 bridge/ble_scan.py --dump     (in mọi gói quảng bá có Manufacturer Data — kiểm tra firmware Remote)
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'common'))
sys.path.insert(0, HERE)
import arscfg  # noqa: E402
import blecodec  # noqa: E402

log = logging.getLogger('ble')


async def power_on(adapter):
    """Bật adapter Bluetooth (BlueZ) nếu đang tắt. Trả về (bus D-Bus, đối tượng adapter)."""
    from dbus_fast import BusType, Variant
    from dbus_fast.aio import MessageBus
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    path = f'/org/bluez/{adapter}'
    obj = bus.get_proxy_object('org.bluez', path, await bus.introspect('org.bluez', path))
    props = obj.get_interface('org.freedesktop.DBus.Properties')
    if not (await props.call_get('org.bluez.Adapter1', 'Powered')).value:
        await props.call_set('org.bluez.Adapter1', 'Powered', Variant('b', True))
        log.info('Đã bật Bluetooth %s', adapter)
    return bus, obj


class ScanController:
    """Dieu phoi cua so scan tren cung adapter hci0.

    Khi server can phat Exact ACK, ta tam dung scan trong mot cua so ngan
    de adapter uu tien radio cho advertising downlink. Sau do scan duoc bat lai
    trong khi ACK van co the tiep tuc advertise den khi ingest gui ACKS -.
    """

    def __init__(self):
        self.scanner = None
        self.running = False
        self.lock = asyncio.Lock()
        self.pause_gen = 0
        self.paused_s = 0.0          # tổng thời gian dừng quét (đo trong mỗi chu kỳ báo trạng thái 5 s)
        self.paused_at = None
        self.pauses = 0

    async def attach_and_start(self, scanner):
        async with self.lock:
            self.scanner = scanner
            await scanner.start()
            self.running = True

    async def pause_for(self, seconds):
        async with self.lock:
            self.pause_gen += 1
            gen = self.pause_gen
            if self.scanner and self.running:
                try:
                    await self.scanner.stop()
                    self.running = False
                    self.paused_at = time.monotonic()
                    self.pauses += 1
                    log.info('DIAG SCAN PAUSE ack_window_ms=%d', round(seconds * 1000))
                except Exception as e:
                    log.warning('Khong tam dung duoc BLE scan: %s', e)
            asyncio.create_task(self._resume_after(seconds, gen))

    async def _resume_after(self, seconds, gen):
        await asyncio.sleep(seconds)
        async with self.lock:
            if gen != self.pause_gen or not self.scanner or self.running:
                return
            try:
                await self.scanner.start()
                self.running = True
                if self.paused_at is not None:
                    self.paused_s += time.monotonic() - self.paused_at
                    self.paused_at = None
                log.info('DIAG SCAN RESUME after_ack_window')
            except Exception as e:
                log.warning('Khong bat lai duoc BLE scan: %s', e)

    def take_duty(self):
        """(số lần dừng, tổng giây dừng) từ lần gọi trước — để log tỉ lệ thời gian không quét."""
        paused = self.paused_s + (time.monotonic() - self.paused_at if self.paused_at is not None else 0.0)
        if self.paused_at is not None:
            self.paused_at = time.monotonic()
        n, self.pauses, self.paused_s = self.pauses, 0, 0.0
        return n, paused

    async def stop(self):
        async with self.lock:
            self.pause_gen += 1
            if self.scanner and self.running:
                try:
                    await self.scanner.stop()
                except Exception:
                    pass
            self.running = False
            self.scanner = None


class Advertiser:
    """Dieu phoi BLE downlink tren mot adapter laptop duy nhat (V3.10.4).

    Nguyen tac V3.10.4:
      * Mac dinh uu tien SCAN uplink; background beacon chi phat burst ngan va
        bo qua cac heartbeat trung nhau trong mot khoang thoi gian.
      * Exact ACK khong con nam tren song suot TTL 1.8 s. Moi ACK chi phat mot
        burst ngan, sau do tat de tra radio ve cho scan.
      * Ban ghi ACK van duoc cache den khi ingest gui ``ACKS -``. Neu Remote
        retry cung transaction, bridge tu re-arm mot ACK burst ma khong can
        ingest phai publish lai noi dung ACK giong het.
      * Trong luc con ACK pending (du da tat song sau burst), background frame
        bi hoan. Day la cua so "pure scan" de bat retry cua Remote.
      * LOGIN cu/da diem danh co the re-arm ATTEND truc tiep tu snapshot dang
        cache, giup LOGIN khong phu thuoc heartbeat 5 s.

    Muc tieu: giam tranh chap scan/advertise tren cung hci0 ma khong doi
    protocol va khong can flash lai firmware Remote V3.10.
    """

    BACKGROUND = (blecodec.F_STATE, blecodec.F_ATTEND, blecodec.F_OPENMASK)
    BG_PRIORITY = (blecodec.F_ATTEND, blecodec.F_STATE, blecodec.F_OPENMASK)

    # ATTEND la xac nhan LOGIN nen duoc phat nhanh va theo mot cua so uu tien rieng.
    # STATE/OPENMASK van la background burst ngan.
    BURST_TTL = {
        blecodec.F_ATTEND: 0.90,
        blecodec.F_STATE: 0.18,
        blecodec.F_OPENMASK: 0.18,
    }
    # Ingest heartbeat mac dinh 5 s. Bridge khong can phat lai y het moi 5 s;
    # 12 s la recovery heartbeat, con thay doi that se phat ngay.
    BG_REFRESH_MIN_S = {
        blecodec.F_ATTEND: 12.0,
        blecodec.F_STATE: 12.0,
        blecodec.F_OPENMASK: 12.0,
    }
    BG_INTER_BURST_GAP_S = 0.12
    BG_AFTER_ACK_CLEAR_S = 0.10

    # V3.10.4: KHONG stop/start scanner cho ACK. Thu nghiem V3.10.3 cho thay
    # full-exclusive 320 ms lam final ACK giam manh du uplink van tot. Ta de
    # controller tu scheduler scan+advertise va giu ACK tren song du lau de nRF
    # co nhieu co hoi bat duoc trong cua so RX 1000 ms.
    ACK_COALESCE_S = 0.02
    ACK_ALIGN_S = 0.02
    ACK_BURST_S = 0.85
    ACK_REARM_MIN_GAP_S = 0.90

    # ATTEND la LOGIN confirmation. Phat lau hon background frame nhung van
    # khong pause scanner de tranh mat uplink/retry do Bleak stop/start.
    LOGIN_ATTEND_ALIGN_S = 0.04

    def __init__(self, adapter, company_id, scan_controller=None):
        self.adapter, self.company = adapter, company_id
        self.bus = self.mgr = None
        self.current = {}          # kind -> bytes dang THUC SU tren song
        self.desired = {}          # kind -> snapshot moi nhat can giu/cache
        self.objs = {}
        self.expire_gen = {}
        self.bg_pending = set()
        self.last_bg_sent_at = {}
        self.last_bg_sent_data = {}
        self.lock = asyncio.Lock()

        # ack_active = ingest van con ban ghi ACK hop le. Khong dong nghia ACK
        # dang advertise; sau ACK_BURST_S, ACK tat song nhung record van cache.
        self.ack_active = False
        self.scan_controller = scan_controller
        self.ack_flush = None
        self.ack_rearm_task = None
        self.login_attend_task = None
        self.last_pause = -1e9
        self.last_ack_pulse = -1e9
        self.ack_pulse_gen = 0
        self.bg_kick_gen = 0

    async def start(self):
        from dbus_fast import Variant
        self.Variant = Variant
        self.bus, obj = await power_on(self.adapter)
        self.mgr = obj.get_interface('org.bluez.LEAdvertisingManager1')

    def _make(self, kind, data):
        from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method
        company, Variant = self.company, self.Variant

        if kind == blecodec.F_ACKS:
            # Dung gan minimum legacy advertising interval de tang xac suat
            # Remote bat duoc packet trong burst full-exclusive ngan.
            min_interval, max_interval = 20, 30
        elif kind == blecodec.F_ATTEND:
            min_interval, max_interval = 40, 60
        else:
            min_interval, max_interval = 180, 260

        class Adv(ServiceInterface):
            def __init__(self):
                super().__init__('org.bluez.LEAdvertisement1')

            @method()
            def Release(self):
                pass

            @dbus_property(access=PropertyAccess.READ)
            def Type(self) -> 's':  # noqa: F821
                return 'broadcast'

            @dbus_property(access=PropertyAccess.READ)
            def ManufacturerData(self) -> 'a{qv}':  # noqa: F821
                return {company: Variant('ay', data)}

            @dbus_property(access=PropertyAccess.READ)
            def MinInterval(self) -> 'u':  # noqa: F821
                return min_interval

            @dbus_property(access=PropertyAccess.READ)
            def MaxInterval(self) -> 'u':  # noqa: F821
                return max_interval

        return f'/ars/adv/k{kind:02x}', Adv()

    async def _deactivate_locked(self, kind):
        """Dung advertisement nhung giu desired de co the pulse lai."""
        path = f'/ars/adv/k{kind:02x}'
        was_active = kind in self.objs or kind in self.current
        if kind in self.objs:
            try:
                await self.mgr.call_unregister_advertisement(path)
            except Exception:
                pass
            try:
                self.bus.unexport(path)
            except Exception:
                pass
            self.objs.pop(kind, None)
        self.current.pop(kind, None)
        if was_active and kind == blecodec.F_ACKS:
            log.info('DIAG ACK ADV STOP')

    async def _activate_locked(self, kind, data):
        if self.current.get(kind) == data:
            return True
        await self._deactivate_locked(kind)
        path, obj = self._make(kind, data)
        self.bus.export(path, obj)
        self.objs[kind] = obj
        try:
            await self.mgr.call_register_advertisement(path, {})
            self.current[kind] = data
            if kind == blecodec.F_ACKS:
                n = data[3] if len(data) >= 4 else 0
                recs = []
                off = 4
                for _ in range(n):
                    if off + 5 > len(data):
                        break
                    seat, qid, seq, ans, status = data[off:off + 5]
                    recs.append(f'{seat}:{qid}:{seq}:{ans}:{status}')
                    off += 5
                log.info('DIAG ACK ADV START room=%s n=%d records=%s interval_ms=20-30 burst_ms=%d scan=continuous',
                         data[2] if len(data) >= 3 else '?', n,
                         ','.join(recs) if recs else '-', round(self.ACK_BURST_S * 1000))
            else:
                self.last_bg_sent_at[kind] = time.monotonic()
                self.last_bg_sent_data[kind] = data
                log.debug('beacon %02X: %s', kind, data.hex())
            return True
        except Exception as e:
            self.current.pop(kind, None)
            self.objs.pop(kind, None)
            try:
                self.bus.unexport(path)
            except Exception:
                pass
            log.warning('Không phát được beacon %02X: %s', kind, e)
            return False

    def _schedule_expiry_locked(self, kind, data):
        ttl = self.BURST_TTL.get(kind)
        if ttl is None:
            return
        gen = self.expire_gen.get(kind, 0) + 1
        self.expire_gen[kind] = gen
        asyncio.create_task(self._expire_after(kind, data, gen, ttl))

    async def _expire_after(self, kind, data, gen, ttl):
        await asyncio.sleep(ttl)
        async with self.lock:
            if self.expire_gen.get(kind) != gen:
                return
            if self.current.get(kind) == data:
                await self._deactivate_locked(kind)
                log.debug('background beacon %02X het burst', kind)
                self._schedule_background_kick_locked(self.BG_INTER_BURST_GAP_S)

    def _schedule_background_kick_locked(self, delay):
        self.bg_kick_gen += 1
        gen = self.bg_kick_gen
        asyncio.create_task(self._background_kick_after(delay, gen))

    async def _background_kick_after(self, delay, gen):
        await asyncio.sleep(delay)
        async with self.lock:
            if gen != self.bg_kick_gen:
                return
            await self._activate_next_background_locked()

    async def _activate_next_background_locked(self):
        # Khi ACK record con song, giu radio o che do pure-scan sau burst ACK.
        # Background se doi toi ACKS - de khong pha cua so retry.
        if self.ack_active or blecodec.F_ACKS in self.current:
            return
        if any(kind in self.current for kind in self.BACKGROUND):
            return
        for kind in self.BG_PRIORITY:
            if kind not in self.bg_pending:
                continue
            data = self.desired.get(kind)
            self.bg_pending.discard(kind)
            if not data:
                continue
            if await self._activate_locked(kind, data):
                self._schedule_expiry_locked(kind, data)
            return

    @staticmethod
    def _records(data):
        """Tap ban ghi (seat, q, seq, answer_code, status) trong mot ACKS frame."""
        if not data or len(data) < 4:
            return set()
        out, off = set(), 4
        for _ in range(data[3]):
            if off + 5 > len(data):
                break
            out.add(tuple(data[off:off + 5]))
            off += 5
        return out

    @staticmethod
    def _answer_code(ans):
        try:
            return blecodec.LETTERS.index(str(ans).upper()) + 1
        except ValueError:
            return 0

    def _ack_contains_pkt(self, data, pkt):
        if not data or pkt.get('type') != blecodec.PKT_ANSWER:
            return False
        code = self._answer_code(pkt.get('ans', ''))
        if not code:
            return False
        target = (int(pkt.get('id', 0)) & 0xFF,
                  int(pkt.get('q', 0)) & 0xFF,
                  int(pkt.get('seq', 0)) & 0xFF,
                  code & 0xFF)
        return any(rec[:4] == target for rec in self._records(data))

    def _attend_has_seat(self, data, seat):
        if not data or len(data) < 4 or data[0] != blecodec.MAGIC or data[1] != blecodec.F_ATTEND:
            return False
        seat = int(seat)
        if seat < 0 or seat > 103:
            return False
        bitmap = data[3:16]
        idx, bit = divmod(seat, 8)
        return idx < len(bitmap) and bool(bitmap[idx] & (1 << bit))

    async def _start_ack_pulse_locked(self, data, reason='new'):
        if not data or len(data) < 4 or data[3] == 0 or not self.ack_active:
            return False

        # Exact ACK preempt background. Frame dang phat bi dua lai queue de sau
        # khi ACK het han ingest (ACKS -) se co the dong bo lai.
        for bg in self.BACKGROUND:
            if bg in self.current:
                self.bg_pending.add(bg)
                await self._deactivate_locked(bg)

        mono = time.monotonic()
        # V3.10.4: khong pause scanner. BlueZ/controller tu chia lich radio cho
        # scan + advertising; ACK burst dai 850 ms de tang xac suat downlink.
        if not await self._activate_locked(blecodec.F_ACKS, data):
            return False

        self.last_ack_pulse = mono
        self.ack_pulse_gen += 1
        gen = self.ack_pulse_gen
        log.info('DIAG ACK PULSE reason=%s duration_ms=%d', reason, round(self.ACK_BURST_S * 1000))
        asyncio.create_task(self._stop_ack_after(self.ACK_BURST_S, gen, data))
        return True

    async def _stop_ack_after(self, delay, gen, data):
        await asyncio.sleep(delay)
        async with self.lock:
            if gen != self.ack_pulse_gen:
                return
            if self.current.get(blecodec.F_ACKS) == data:
                await self._deactivate_locked(blecodec.F_ACKS)
                # Khong restore background o day. ack_active van True, nen tu
                # day den ACKS - radio gan nhu pure-scan de bat retry.
                log.info('DIAG ACK PULSE END -> pure scan while ACK record cached')

    async def _flush_ack_later(self):
        await asyncio.sleep(self.ACK_COALESCE_S + self.ACK_ALIGN_S)
        async with self.lock:
            data = self.desired.get(blecodec.F_ACKS)
            if not data or not self.ack_active:
                return
            if self.current.get(blecodec.F_ACKS) == data:
                return

            new = self._records(data) - self._records(self.current.get(blecodec.F_ACKS))
            for rec in sorted(new):
                seat, qid, seq, ans, status = rec
                log.info('DIAG ACK QUEUED seat=%d q=%d seq=%03d ans_code=%d status=%d',
                         seat, qid, seq, ans, status)

            await self._start_ack_pulse_locked(data, 'new')

            # Neu desired doi trong luc D-Bus dang register, lap them mot lan.
            if self.ack_active and self.desired.get(blecodec.F_ACKS) not in (None, self.current.get(blecodec.F_ACKS)):
                self.ack_flush = asyncio.create_task(self._flush_ack_later())

    async def _rearm_ack_after(self, delay, expected_data, pkt):
        await asyncio.sleep(delay)
        async with self.lock:
            if not self.ack_active or self.desired.get(blecodec.F_ACKS) != expected_data:
                return
            if self.current.get(blecodec.F_ACKS) == expected_data:
                return
            if time.monotonic() - self.last_ack_pulse < self.ACK_REARM_MIN_GAP_S:
                return
            if not self._ack_contains_pkt(expected_data, pkt):
                return
            log.info('DIAG ACK REARM seat=%d q=%d seq=%03d ans=%s',
                     int(pkt.get('id', 0)), int(pkt.get('q', 0)), int(pkt.get('seq', 0)), pkt.get('ans', '-'))
            await self._start_ack_pulse_locked(expected_data, 'retry')

    async def _pulse_attend_after_login(self, delay, seat):
        await asyncio.sleep(delay)
        async with self.lock:
            if self.ack_active:
                return
            data = self.desired.get(blecodec.F_ATTEND)
            if not self._attend_has_seat(data, seat):
                return
            # ATTEND la xac nhan LOGIN. Cho phep preempt background khac.
            active_bg = next((bg for bg in self.BACKGROUND if bg in self.current), None)
            if active_bg == blecodec.F_ATTEND and self.current.get(active_bg) == data:
                return
            if active_bg is not None:
                self.bg_pending.add(active_bg)
                await self._deactivate_locked(active_bg)
            self.bg_pending.discard(blecodec.F_ATTEND)
            # V3.10.4: khong pause scanner; ATTEND pulse 900 ms de Remote co
            # nhieu co hoi bat bit attendance trong RX window.
            if await self._activate_locked(blecodec.F_ATTEND, data):
                self._schedule_expiry_locked(blecodec.F_ATTEND, data)
                log.info('DIAG ATTEND REARM seat=%d after LOGIN retry burst_ms=%d',
                         int(seat), round(self.BURST_TTL[blecodec.F_ATTEND] * 1000))

    async def notify_uplink(self, pkt):
        """Thong bao packet vua nghe duoc de re-arm downlink ma khong doi protocol.

        Bleak co the bao nhieu ban sao trong cung mot TX burst. Cac guard/task
        ben duoi dam bao mot burst uplink khong tao hang loat D-Bus register.
        """
        if not self.mgr:
            return

        ptype = pkt.get('type')
        if ptype == blecodec.PKT_ANSWER:
            async with self.lock:
                data = self.desired.get(blecodec.F_ACKS)
                if (not self.ack_active or not self._ack_contains_pkt(data, pkt)
                        or blecodec.F_ACKS in self.current):
                    return
                if self.ack_flush is not None and not self.ack_flush.done():
                    return
                if self.ack_rearm_task is not None and not self.ack_rearm_task.done():
                    return
                if time.monotonic() - self.last_ack_pulse < self.ACK_REARM_MIN_GAP_S:
                    return
                self.ack_rearm_task = asyncio.create_task(
                    self._rearm_ack_after(self.ACK_ALIGN_S, data, dict(pkt)))
            return

        if ptype == blecodec.PKT_LOGIN:
            async with self.lock:
                if self.ack_active:
                    return
                data = self.desired.get(blecodec.F_ATTEND)
                seat = int(pkt.get('id', 0))
                if not self._attend_has_seat(data, seat):
                    return
                if self.login_attend_task is not None and not self.login_attend_task.done():
                    return
                self.login_attend_task = asyncio.create_task(
                    self._pulse_attend_after_login(self.LOGIN_ATTEND_ALIGN_S, seat))

    async def set(self, kind, data):
        async with self.lock:
            if not self.mgr:
                return

            if kind == blecodec.F_ACKS:
                empty = len(data) >= 4 and data[3] == 0
                if empty:
                    if not self.ack_active and kind not in self.current:
                        return
                    self.desired.pop(kind, None)
                    self.ack_active = False
                    self.ack_pulse_gen += 1       # huy timer pulse cu neu con
                    log.info('DIAG ACK CLEAR received_empty_acks')
                    await self._deactivate_locked(kind)
                    # Chi luc ACK het TTL moi cho background quay lai.
                    self._schedule_background_kick_locked(self.BG_AFTER_ACK_CLEAR_S)
                    return

                old = self.desired.get(kind)
                self.desired[kind] = data
                self.ack_active = True
                # MQTT retained/state co the lap lai dung payload dang cache.
                # Neu khong co uplink retry thi khong tu pulse lai vo ich.
                if old == data and kind not in self.current:
                    return
                if self.current.get(kind) != data and (self.ack_flush is None or self.ack_flush.done()):
                    self.ack_flush = asyncio.create_task(self._flush_ack_later())
                return

            # Background: snapshot thay doi phat ngay; heartbeat y het chi phat
            # lai sau BG_REFRESH_MIN_S de giam airtime.
            old = self.desired.get(kind)
            self.desired[kind] = data
            now = time.monotonic()
            changed = old != data
            refresh_due = (now - self.last_bg_sent_at.get(kind, -1e9)
                           >= self.BG_REFRESH_MIN_S.get(kind, 12.0))
            if not changed and not refresh_due:
                return
            self.bg_pending.add(kind)

            if self.ack_active or blecodec.F_ACKS in self.current:
                return

            active_bg = next((bg for bg in self.BACKGROUND if bg in self.current), None)
            if active_bg is not None:
                if active_bg == kind and self.current.get(kind) == data:
                    self.bg_pending.discard(kind)
                    return
                rank = {k: i for i, k in enumerate(self.BG_PRIORITY)}
                if rank.get(kind, 99) >= rank.get(active_bg, 99):
                    return
                self.bg_pending.add(active_bg)
                await self._deactivate_locked(active_bg)

            # Khi attendance THAY DOI (thuong la LOGIN moi), cap cho no mot
            # cua so TX-only ngay ca truoc khi Remote phai retry LOGIN.
            if kind == blecodec.F_ATTEND and changed:
                log.info('DIAG ATTEND PRIORITY changed_bitmap burst_ms=%d',
                         round(self.BURST_TTL[blecodec.F_ATTEND] * 1000))

            await self._activate_next_background_locked()

async def run(a, cp):
    from bleak import BleakScanner
    room = int(cp['gateway']['room'])
    bc = cp['ble'] if cp.has_section('ble') else {}
    adapter = a.adapter or bc.get('adapter', 'hci0')
    company = int(str(bc.get('company_id', '0xFFFF')), 0)
    advertise = str(bc.get('advertise', '1')) not in ('0', 'no', 'false') and sys.platform.startswith('linux') and not a.dump
    loop = asyncio.get_running_loop()
    status_topic = f'ars/{room}/gw/status'
    counters = {'n': 0}

    scan_ctl = ScanController()
    adv = Advertiser(adapter, company, scan_ctl) if advertise else None
    if not adv and sys.platform.startswith('linux'):
        try:
            await power_on(adapter)
        except Exception as e:
            log.warning('Không bật được Bluetooth %s: %s', adapter, e)
    if adv:
        # V3.10.4: bidirectional mode bat buoc ca scan va advertise.
        # Nếu BlueZ/hci0 chưa sẵn sàng lúc boot thì KHÔNG rơi vĩnh viễn vào
        # chế độ uplink-only; chờ và thử lại cho tới khi advertiser sẵn sàng.
        while True:
            try:
                await adv.start()
                log.info('DIAG BLE TX READY adapter=%s', adapter)
                log.info('DIAG V3.10.4 RADIO ack_burst_ms=%d attend_burst_ms=%d scan=continuous',
                         round(adv.ACK_BURST_S * 1000),
                         round(adv.BURST_TTL[blecodec.F_ATTEND] * 1000))
                break
            except Exception as e:
                log.warning('BLE advertiser %s chưa sẵn sàng (%s) - thử lại sau 3 s', adapter, e)
                await asyncio.sleep(3)

    def apply(lines):
        for line in lines:
            enc = blecodec.encode_cmd(line, room)
            if enc and adv:
                asyncio.run_coroutine_threadsafe(adv.set(*enc), loop)

    cli = None
    if not a.dump:
        cli = arscfg.mqtt_client(f'ars-ble-{room}', clean_session=True)
        cli.will_set(status_topic, json.dumps({'online': False}), qos=1, retain=True)

        def on_connect(c, u, f, rc):
            log.info('MQTT đã kết nối (rc=%s)', rc)
            c.subscribe(f'ars/{room}/cmd/gw', qos=1)
            c.subscribe(f'ars/{room}/state', qos=1)

        def on_message(c, u, msg):
            if msg.topic.endswith('/cmd/gw'):
                apply([msg.payload.decode('ascii', 'replace')])
            else:
                try:
                    apply(json.loads(msg.payload).get('cmds', []))
                except ValueError:
                    pass
        cli.on_connect, cli.on_message = on_connect, on_message
        cli.connect(cp['mqtt']['host'], int(cp['mqtt'].get('port', 1883)), keepalive=30)
        cli.loop_start()

    def on_adv(device, ad):
        for cid, data in (ad.manufacturer_data or {}).items():
            if a.dump:
                print(f'{device.address}  rssi={ad.rssi}  company=0x{cid:04X}  data={bytes(data).hex()}', flush=True)
            if cid != company:
                continue
            pkt = blecodec.decode_uplink(data, device.address, ad.rssi)
            if not pkt:
                continue
            if a.dump:
                print('   → ARS', json.dumps(pkt), flush=True)
                continue
            pkt['ts'] = time.time()
            pkt['via'] = 'ble'
            if pkt.get('type') == blecodec.PKT_ANSWER:
                log.info('DIAG RF RX ANSWER room=%d seat=%d q=%d seq=%03d ans=%s rssi=%s',
                         pkt.get('room', 0), pkt.get('id', 0), pkt.get('q', 0), pkt.get('seq', 0),
                         pkt.get('ans', '-'), pkt.get('rssi'))
            elif pkt.get('type') == blecodec.PKT_LOGIN:
                log.info('DIAG RF RX LOGIN room=%d seat=%d seq=%03d rssi=%s',
                         pkt.get('room', 0), pkt.get('id', 0), pkt.get('seq', 0), pkt.get('rssi'))
            cli.publish(f"ars/{pkt['room']}/resp", json.dumps(pkt), qos=1)
            # V3.10.3: neu day la retry cua mot transaction da co ACK cache,
            # bridge co the pulse lai ACK ngay ca khi ingest khong publish lai
            # payload ACK giong het. LOGIN cu cung co the re-arm ATTEND.
            if adv:
                asyncio.run_coroutine_threadsafe(adv.notify_uplink(pkt), loop)
            counters['n'] += 1

    kw = {'detection_callback': on_adv, 'scanning_mode': 'active'}
    if sys.platform.startswith('linux'):
        kw['adapter'] = adapter
        kw['bluez'] = {'filters': {'Transport': 'le', 'DuplicateData': True}}   # báo cả gói lặp (gói lặp cùng seq = gửi lại)
    while True:                                           # Bluetooth tat / adapter mat -> thu lai
        scanner = BleakScanner(**kw)
        try:
            await scan_ctl.attach_and_start(scanner)
            log.info('Dang nghe Remote qua Bluetooth %s (room %d, company 0x%04X)%s', adapter, room, company,
                     ', V3.10.4 continuous scan + long bounded ACK/ATTEND + retry re-arm' if adv else '')
            while True:
                await asyncio.sleep(5)
                n, counters['n'] = counters['n'], 0
                np, ps = scan_ctl.take_duty()
                if np:
                    log.info('DIAG SCAN DUTY pauses=%d paused_ms=%d of 5000 (%.0f%% scanning)', np, round(ps * 1000), 100 - ps * 20)
                if cli:
                    cli.publish(status_topic, json.dumps({'online': True, 'port': f'bluetooth {adapter}',
                                                          'pkt_per_s': round(n / 5, 1), 'ts': time.time()}), qos=1, retain=True)
        except Exception as e:
            log.warning('Bluetooth %s: %s - thu lai sau 3 s', adapter, e)
            if cli:
                cli.publish(status_topic, json.dumps({'online': False, 'port': f'bluetooth {adapter}', 'ts': time.time()}), qos=1, retain=True)
            await asyncio.sleep(3)
        finally:
            await scan_ctl.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config')
    ap.add_argument('--adapter', help='hci0, hci1… (Linux)')
    ap.add_argument('--dump', action='store_true', help='in mọi gói quảng bá có Manufacturer Data, không gửi MQTT')
    a = ap.parse_args()
    cp = arscfg.load(a.config)
    try:
        asyncio.run(run(a, cp))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    main()
