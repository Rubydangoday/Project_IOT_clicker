#!/usr/bin/env python3
"""V3.12: one BLE UART remote; Room is selected by the remote, not config.ini.

--scan: discover only. --probe 100: PING/PONG only, never fabricate a DB ACK.
No BlueZ advertising API, Experimental setting, or separate RF gateway needed.
"""
import argparse
import asyncio
import contextlib
import json
import logging
import os
import struct
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
import arscfg
import blecodec
from gatt_protocol import Decoder, Transactions, frame, SERVICE_UUID, RX_UUID, TX_UUID, HELLO, HELLO_REPLY, PING, PONG
log = logging.getLogger('gatt')


async def discover(adapter):
    from bleak import BleakScanner
    kw = {'adapter': adapter} if sys.platform.startswith('linux') else {}
    return await BleakScanner.discover(timeout=5, return_adv=True, **kw)


def candidates(found, address, name):
    out = []
    for dev, adv in found.values():
        if address:
            match = dev.address.upper() == address.upper()
        else:
            match = (adv.local_name or dev.name) == name and SERVICE_UUID in [u.lower() for u in adv.service_uuids]
        if match:
            out.append(dev)
    return out


class Link:
    def __init__(self, cp, room, probe=0):
        self.cp, self.room, self.probe = cp, room, probe
        self.client = None
        self.mqtt = None
        self.mqtt_ready = asyncio.Event()
        self.ready = False
        self.lost = asyncio.Event()
        self.decoder = Decoder()
        self.txns = None
        self.queue = asyncio.PriorityQueue(maxsize=64)
        self.serial = 0
        self.write_lock = asyncio.Lock()
        self.hello = asyncio.Event()
        self.last_hello_reply = 0
        self.room_reply = asyncio.Event()
        self.remote_room = None
        self.generation = 0
        self.device_address = None
        self.pong_waiters = {}
        self.snapshots = {}
        self.count = 0
        self.port = 'BLE GATT disconnected'

    def status(self):
        if self.mqtt and self.mqtt_ready.is_set():
            online = bool(self.ready and self.client and self.client.is_connected)
            info = self.mqtt.publish(f'ars/{self.room}/gw/status', json.dumps({
                'online': online, 'port': self.port, 'pkt_per_s': round(self.count / 2, 1), 'ts': time.time()}), qos=1, retain=True)
            self.count = 0
            return info
        return None

    async def start_mqtt(self):
        """One broker client per selected room, with its own correct Last Will.

        Switching rooms replaces MQTT only, while keeping the BLE connection.
        Late callbacks from an old broker client cannot affect the new room.
        """
        loop = asyncio.get_running_loop()
        selected_room = self.room
        client = arscfg.mqtt_client(f'ars-gatt-{selected_room}', clean_session=True)
        self.mqtt = client
        self.mqtt_ready.clear()
        client.will_set(f'ars/{selected_room}/gw/status', json.dumps({
            'online': False, 'port': self.port}), qos=1, retain=True)

        def subscribed():
            if client is self.mqtt and selected_room == self.room:
                self.mqtt_ready.set()

        def disconnected():
            if client is self.mqtt:
                self.mqtt_ready.clear()
                self.lost.set()

        def deliver(topic, payload, retained):
            if client is self.mqtt and selected_room == self.room:
                self.on_mqtt(topic, payload, retained)

        def on_connect(c, u, flags, rc):
            if c is not self.mqtt:
                return
            if rc != 0:
                log.error('MQTT connect rc=%s', rc)
                loop.call_soon_threadsafe(disconnected)
                return
            c.subscribe([(f'ars/{selected_room}/state', 1),
                         (f'ars/{selected_room}/cmd/gw', 1),
                         (f'ars/{selected_room}/result/gatt', 1)])

        def on_subscribe(c, u, mid, granted_qos):
            if any(int(q) >= 128 for q in granted_qos):
                log.error('MQTT subscription rejected for room=%s', selected_room)
                loop.call_soon_threadsafe(disconnected)
            else:
                loop.call_soon_threadsafe(subscribed)

        def on_disconnect(c, u, rc):
            loop.call_soon_threadsafe(disconnected)

        def on_message(c, u, msg):
            loop.call_soon_threadsafe(deliver, msg.topic, bytes(msg.payload), bool(msg.retain))

        client.on_connect = on_connect
        client.on_subscribe = on_subscribe
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.connect_async(self.cp['mqtt']['host'], int(self.cp['mqtt'].get('port', 1883)), 30)
        client.loop_start()
        await self.wait_event(self.mqtt_ready, 15, 'MQTT subscriptions')
        self.status()

    async def stop_mqtt(self):
        """Mark the previous room offline; then retire all its callbacks."""
        client = self.mqtt
        if not client:
            return
        self.ready = False
        info = self.status()
        # Detach BEFORE disconnect: an intentional switch must not end BLE.
        self.mqtt = None
        self.mqtt_ready.clear()
        try:
            if info is not None:
                await asyncio.to_thread(info.wait_for_publish, 2)
        except (RuntimeError, ValueError):
            log.warning('Old-room offline status was not confirmed by MQTT')
        finally:
            client.disconnect()
            await asyncio.to_thread(client.loop_stop)

    async def wait_event(self, event, timeout, label):
        """Fail immediately on link loss rather than waiting out a HELLO timeout."""
        waiter = asyncio.create_task(event.wait())
        lost = asyncio.create_task(self.lost.wait())
        try:
            done, _ = await asyncio.wait([waiter, lost], timeout=timeout,
                                         return_when=asyncio.FIRST_COMPLETED)
            if self.lost.is_set():
                raise ConnectionError(f'Connection lost during {label}')
            if waiter not in done:
                raise TimeoutError(f'{label} timed out after {timeout}s')
        finally:
            waiter.cancel()
            lost.cancel()
            await asyncio.gather(waiter, lost, return_exceptions=True)

    async def exchange_hello(self, requested_room):
        self.room_reply.clear()
        await self.write(bytes([0xA5, HELLO, requested_room]))
        await self.wait_event(self.room_reply, 5, 'HELLO reply')
        return self.remote_room

    def clear_room_state(self):
        self.ready = False
        self.hello.clear()
        self.generation += 1
        self.txns = None
        self.snapshots.clear()
        while not self.queue.empty():
            self.queue.get_nowait()

    async def select_room(self, requested_room):
        """Adopt the remote identity without disconnecting the BLE radio.

        HELLO 0 discovers/suspends a V3.11 remote. It can then be authorized
        only after the new MQTT subscriptions and transaction scope are ready.
        """
        while True:
            previous = self.room
            self.clear_room_state()
            await self.stop_mqtt()
            self.room = requested_room
            self.txns = Transactions(self.room, self.device_address)
            log.info('ROOM SELECT remote=%s previous=%s; BLE kept connected', self.room, previous)
            await self.start_mqtt()
            # Readiness is provisional until a matching HELLO reply. This lets
            # LOGIN arriving immediately after that reply reach the backend.
            self.ready = True
            actual_room = await self.exchange_hello(self.room)
            if actual_room != self.room:
                # User may edit Room again while MQTT is subscribing.
                requested_room = actual_room
                continue
            if self.lost.is_set():
                raise ConnectionError('Connection lost while selecting room')
            for data in self.snapshots.values():
                self.enqueue(data)
            self.status()
            log.info('GATT READY %s room=%s (remote-selected)', self.device_address, self.room)
            return

    def enqueue(self, payload, priority=1):
        if not self.ready:
            return
        self.serial += 1
        try:
            self.queue.put_nowait((priority, self.serial, payload, self.generation))
        except asyncio.QueueFull:
            log.error('Downlink queue full; reconnect instead of silently losing a result')
            self.lost.set()

    def on_mqtt(self, topic, payload, retained):
        # Never let delayed or unrelated room traffic cross the room boundary.
        if topic not in (f'ars/{self.room}/state', f'ars/{self.room}/cmd/gw',
                         f'ars/{self.room}/result/gatt'):
            return
        try:
            if topic.endswith('/result/gatt'):
                if retained or not self.ready or not self.txns:
                    return
                result = json.loads(payload)
                encoded = self.txns.result(result)
                if encoded:
                    log.info('BACKEND RESULT type=%s seq=%s status=%s', result['type'], result['seq'], result['status'])
                    self.enqueue(encoded, 0)
                return
            if topic.endswith('/state'):
                lines = json.loads(payload).get('cmds', [])
            else:
                lines = [payload.decode('ascii')]
            for line in lines:
                encoded = blecodec.encode_cmd(line, self.room)
                if not encoded:
                    continue
                kind, data = encoded
                if len(data) < 3 or data[2] != self.room:
                    continue
                # Exact results arrive ONLY on /result/gatt, never from cached state.
                if kind not in (blecodec.F_STATE, blecodec.F_OPENMASK):
                    continue
                if self.snapshots.get(kind) != data:
                    self.snapshots[kind] = data
                    self.enqueue(data)
        except (ValueError, TypeError, KeyError, AttributeError):
            log.warning('Ignoring malformed MQTT message on %s', topic)

    def on_notify(self, sender, data):
        try:
            for payload in self.decoder.feed(data):
                kind = payload[1]
                if kind == PONG and len(payload) == 6:
                    fut = self.pong_waiters.get(payload[2:])
                    if fut and not fut.done():
                        fut.set_result(time.perf_counter())
                elif kind == HELLO_REPLY and len(payload) == 4:
                    reported_room = payload[2]
                    if not 1 <= reported_room <= 99:
                        log.error('Invalid remote Room=%s; enter 01..99', reported_room)
                        self.lost.set()
                        continue
                    self.remote_room = reported_room
                    self.last_hello_reply = time.monotonic()
                    if reported_room != self.room:
                        self.ready = False
                        self.hello.clear()
                    elif self.mqtt_ready.is_set():
                        self.hello.set()
                    self.room_reply.set()
                elif kind in (1, 2) and self.txns and not self.probe:
                    # HELLO authorizes the remote; its LOGIN can follow in the same event.
                    if not self.ready or not self.hello.is_set() or not self.mqtt_ready.is_set():
                        continue
                    pkt = self.txns.request(payload)
                    info = self.mqtt.publish(f'ars/{self.room}/resp', json.dumps(pkt), qos=1)
                    if info.rc != 0:
                        raise RuntimeError(f'MQTT publish failed: {info.rc}')
                    self.count += 1
                    log.info('GATT RX room=%d type=%d seat=%d q=%d seq=%03d ans=%s', pkt['room'], pkt['type'], pkt['id'], pkt['q'], pkt['seq'], pkt['ans'])
        except (ValueError, RuntimeError) as e:
            log.error('RX failed: %s', e)
            self.lost.set()

    async def write(self, payload, generation=None):
        packet = frame(payload)
        if len(packet) > 20:
            raise ValueError('Single-remote packet exceeds default ATT payload')
        async with self.write_lock:
            if generation is not None and (generation != self.generation or not self.ready
                                            or len(payload) < 3 or payload[2] != self.room):
                return
            await asyncio.wait_for(self.client.write_gatt_char(RX_UUID, packet, response=True), 3)

    async def writer(self):
        while True:
            _, _, payload, generation = await self.queue.get()
            await self.write(payload, generation)

    async def heartbeat(self):
        while True:
            await asyncio.sleep(2)
            if not self.mqtt_ready.is_set():
                raise ConnectionError('MQTT connection lost')
            actual_room = await self.exchange_hello(self.room)
            if actual_room != self.room:
                await self.select_room(actual_room)
            self.status()

    async def probe_link(self):
        samples = []
        for seq in range(self.probe):
            token = struct.pack('<I', seq)
            fut = asyncio.get_running_loop().create_future()
            self.pong_waiters[token] = fut
            start = time.perf_counter()
            await self.write(bytes([0xA5, PING]) + token)
            try:
                end = await asyncio.wait_for(fut, 2)
                samples.append((end - start) * 1000)
            finally:
                self.pong_waiters.pop(token, None)
            await asyncio.sleep(0.05)
        samples.sort()
        print(json.dumps({'ping_pong_ok': len(samples), 'requested': self.probe,
                          'median_ms': round(samples[len(samples)//2], 1),
                          'p95_ms': round(samples[max(0, (95*len(samples)+99)//100-1)], 1),
                          'max_ms': round(samples[-1], 1),
                          'note': 'BLE round trip only; does not test database/answer ACK'}, indent=2))

    async def session(self, device, adapter):
        from bleak import BleakClient
        self.lost = asyncio.Event()
        self.hello = asyncio.Event()
        self.decoder = Decoder()
        self.queue = asyncio.PriorityQueue(maxsize=64)
        self.device_address = device.address
        self.remote_room = None
        self.room_reply = asyncio.Event()
        self.clear_room_state()
        self.ready = False
        self.port = f'BLE GATT {device.address}'
        loop = asyncio.get_running_loop()
        kw = {'adapter': adapter} if sys.platform.startswith('linux') else {}
        tasks = []
        try:
            async with BleakClient(device, disconnected_callback=lambda _: loop.call_soon_threadsafe(self.lost.set), **kw) as client:
                self.client = client
                await client.start_notify(TX_UUID, self.on_notify)
                if self.probe:
                    await self.probe_link()
                    return
                # Room 0 is discovery only: existing firmware replies with its
                # saved Room but cannot send application packets yet.
                requested_room = await self.exchange_hello(0)
                await self.select_room(requested_room)
                tasks = [asyncio.create_task(self.writer()), asyncio.create_task(self.heartbeat()), asyncio.create_task(self.lost.wait())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
        finally:
            self.ready = False
            self.status()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.stop_mqtt()
            self.client = None
            self.txns = None



async def run(args):
    import configparser
    if args.scan or args.probe:
        cp = arscfg.load(args.config) if args.config else configparser.ConfigParser()
    else:
        cp = arscfg.load(args.config)
    bc = cp['ble'] if cp.has_section('ble') else {}
    room = 1  # Bootstrap placeholder only; HELLO reads the actual remote Room.
    adapter = args.adapter or bc.get('adapter', 'hci0')
    address = args.address or bc.get('remote_address', '').strip()
    name = bc.get('remote_name', 'ARS_REMOTE_01')
    link = Link(cp, room, args.probe)
    try:
        while True:
            found = await discover(adapter)
            if args.scan:
                for dev, adv in found.values():
                    if SERVICE_UUID in [u.lower() for u in adv.service_uuids] or (adv.local_name or dev.name) == name:
                        print(dev.address, adv.local_name or dev.name, 'RSSI', adv.rssi, 'services', adv.service_uuids)
                return
            devices = candidates(found, address, name)
            if len(devices) > 1:
                raise RuntimeError('Multiple matching remotes: set [ble] remote_address explicitly')
            if not devices:
                if args.probe:
                    raise RuntimeError('Remote not found: flash V3.11, close other BLE apps, run --scan')
                log.warning('Waiting for remote %s', address or name)
                await asyncio.sleep(2)
                continue
            address = devices[0].address  # pin to this remote for reconnect in this process
            try:
                await link.session(devices[0], adapter)
                if args.probe:
                    return
            except Exception:
                log.exception('GATT session failed')
                if args.probe:
                    raise
            log.warning('Disconnected; reconnecting to %s', address)
            await asyncio.sleep(2)
    finally:
        await link.stop_mqtt()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config')
    p.add_argument('--adapter')
    p.add_argument('--address')
    p.add_argument('--scan', action='store_true')
    p.add_argument('--probe', type=int, default=0, metavar='N')
    args = p.parse_args()
    if args.probe < 0 or args.probe > 10000:
        p.error('--probe must be 1..10000')
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    main()
