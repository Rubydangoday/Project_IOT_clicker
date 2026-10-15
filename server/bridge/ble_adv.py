#!/usr/bin/env python3
"""V3.18 experimental multi-remote advertising bridge for Linux.
One advertised page at a time, scanner NEVER deliberately paused for ACK.
Actual simultaneous RX/TX scheduling and advertising interval require RF testing.
"""
import argparse
import asyncio
import contextlib
import json
import logging
import sys
import time
from collections import OrderedDict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
import arscfg
from adv_protocol import COMPANY, MAGIC, STATE, ResultQueue, canonical, decode, state_frame
log=logging.getLogger('adv16')


class Radio:
    def __init__(self,adapter,interval):
        self.adapter=adapter;self.interval=interval;self.current=None;self.path='/ars/adv16/page'
        self.bus=None;self.registered=False

    async def start(self):
        from dbus_fast import BusType,Variant
        from dbus_fast.aio import MessageBus
        self.Variant=Variant
        self.bus=await MessageBus(bus_type=BusType.SYSTEM).connect()
        path=f'/org/bluez/{self.adapter}'
        obj=self.bus.get_proxy_object('org.bluez',path,await self.bus.introspect('org.bluez',path))
        props=obj.get_interface('org.freedesktop.DBus.Properties')
        await props.call_set('org.bluez.Adapter1','Powered',Variant('b',True))
        self.manager=obj.get_interface('org.bluez.LEAdvertisingManager1')
        count=(await props.call_get('org.bluez.LEAdvertisingManager1','SupportedInstances')).value
        if count<1:raise RuntimeError('Adapter has no advertising instance')
        log.info('Adapter=%s supported_instances=%s interval_requested_ms=%s (verify actual with btmon)',
                 self.adapter,count,self.interval)

    async def show(self,data):
        if self.current==data:return
        await self.clear()
        if data is None:return
        from dbus_fast.service import ServiceInterface,dbus_property,method,PropertyAccess
        Variant=self.Variant;interval=self.interval
        class Page(ServiceInterface):
            def __init__(self):super().__init__('org.bluez.LEAdvertisement1')
            @method()
            def Release(self):pass
            @dbus_property(access=PropertyAccess.READ)
            def Type(self)->'s':return 'broadcast'
            @dbus_property(access=PropertyAccess.READ)
            def ManufacturerData(self)->'a{qv}':return {COMPANY:Variant('ay',data)}
            @dbus_property(access=PropertyAccess.READ)
            def MinInterval(self)->'u':return interval
            @dbus_property(access=PropertyAccess.READ)
            def MaxInterval(self)->'u':return interval
        self.bus.export(self.path,Page())
        try:
            await self.manager.call_register_advertisement(self.path,{})
            self.registered=True;self.current=data
        except BaseException:
            self.bus.unexport(self.path);raise

    async def clear(self):
        if self.registered:
            await self.manager.call_unregister_advertisement(self.path)
            self.bus.unexport(self.path)
            self.registered=False;self.current=None

    async def close(self):
        try:await self.clear()
        finally:
            if self.bus:self.bus.disconnect()


class Bridge:
    def __init__(self,drop_up=0,drop_result=0):
        self.mqtt=None;self.online=False;self.sub_mid=None
        self.requests=OrderedDict();self.states=OrderedDict();self.results=ResultQueue()
        self.latest={}
        self.last_state_slot=-1e9;self.up_count=0;self.result_count=0
        self.drop_up=drop_up;self.drop_result=drop_result;self.dropped_results=set()

    def receive(self,mac,data,rssi,now=None):
        now=time.monotonic() if now is None else now
        if not self.online:return
        try:p=decode(data,mac,rssi)
        except (ValueError,TypeError):return
        key=(p['mac'],p['adv_token']);body=canonical(p)
        for k in list(self.requests):
            if now-self.requests[k]['seen']>60:
                self.requests.pop(k);self.dropped_results.discard(k)
                if self.latest.get(k[0])==k:self.latest.pop(k[0],None)
        record=self.requests.get(key)
        if record and record['body']!=body:
            log.error('Token reused with different payload: %s',key);return
        if record is None:
            if len(self.requests)>=2048:
                log.error('Request queue full; remote must retry');return
            self.up_count+=1
            drop=bool(self.drop_up and self.up_count%self.drop_up==0)
            record=dict(body=body,pkt=p,seen=now,first=now,last=-1e9,mute=now+0.8 if drop else now)
            self.requests[key]=record
            previous=self.requests.get(self.latest.get(p['mac']))
            if previous:
                old=previous['pkt'];self.results.items.pop((old['room'],old['adv_token']),None)
            self.latest[p['mac']]=key
            log.info('ADV RX token=%s type=%s room=%s seat=%s q=%s ans=%s rssi=%s injected_drop=%s',
                     p['adv_token'],p['type'],p['room'],p['id'],p['q'],p['ans'],rssi,drop)
        record['seen']=now
        if now<record['mute'] or now-record['last']<0.75:return
        info=self.mqtt.publish(f"ars/{p['room']}/resp",json.dumps(p),qos=1,retain=False)
        if not info.rc:record['last']=now

    def message(self,topic,payload,retained=False,now=None,wall=None):
        if not self.online:return
        now=time.monotonic() if now is None else now
        wall=time.time() if wall is None else wall
        try:
            obj=json.loads(payload);parts=topic.split('/');room=int(parts[1])
            if not 1<=room<=99:return
            if parts==['ars',str(room),'state']:
                if obj['room']!=room or not -5<=wall-float(obj['ts'])<=15:return
                data=state_frame(obj)
                self.states[room]=(data,now+max(0,15-(wall-float(obj['ts']))))
                return
            if parts!=['ars',str(room),'result','adv16'] or retained:return
            if obj['room']!=room:return
            key=(obj['mac'],obj['adv_token']);rec=self.requests.get(key)
            if not rec or now-rec['seen']>60 or canonical(obj)!=rec['body']:return
            if self.latest.get(obj['mac'])!=key:return
            status=obj['status']
            if not isinstance(status,int) or not 0<=status<=255:return
            if key not in self.dropped_results and self.drop_result:
                self.result_count+=1;self.dropped_results.add(key)
                if self.result_count%self.drop_result==0:
                    log.warning('INJECT dropped backend result token=%s',obj['adv_token']);return
            self.results.put(room,obj['adv_token'],status,now)
            log.info('ADV RESULT token=%s status=%s rx_to_backend_ms=%.1f',obj['adv_token'],status,
                     (now-rec['first'])*1000)
        except (ValueError,KeyError,TypeError,OverflowError) as e:
            log.warning('Ignored MQTT message: %s',e)

    def page(self,now=None):
        now=time.monotonic() if now is None else now
        if not self.online:return None
        for r in list(self.states):
            if self.states[r][1]<=now:del self.states[r]
        self.results.expire(now)
        if self.states and now-self.last_state_slot>=1:
            room=next(iter(self.states));data=self.states[room][0];self.states.move_to_end(room)
            self.last_state_slot=now
            return data
        return self.results.page(now)

    def page_registered(self,data,now=None):
        """BlueZ registration timestamp, NOT proof of an over-the-air TX."""
        if not data or data[1]==STATE:return
        now=time.monotonic() if now is None else now
        tokens={data[4+9*i:12+9*i].hex() for i in range(data[3])}
        for rec in self.requests.values():
            p=rec['pkt']
            if p['room']==data[2] and p['adv_token'] in tokens and not rec.get('page_logged'):
                rec['page_logged']=True
                log.info('ADV ACK_PAGE_REGISTERED token=%s rx_to_page_ms=%.1f (not RF timestamp)',
                         p['adv_token'],(now-rec['first'])*1000)

    def disconnected(self):
        self.online=False;self.states.clear();self.results.items.clear()


async def transmit_page(radio,bridge,data,page_ms,rx_gap_ms,sleep=asyncio.sleep):
    # Scanning remains requested throughout. Explicitly stop downlink advertising
    # between pulses so the adapter gets a receive-only opportunity.
    if data is None:
        await radio.show(None)
        await sleep(.02)
        return
    await radio.show(data)
    bridge.page_registered(data)
    await sleep(page_ms/1000)
    await radio.clear()
    await sleep(rx_gap_ms/1000)


async def run(args):
    cp=arscfg.load(args.config)
    bc=cp['ble'] if cp.has_section('ble') else {}
    adapter=args.adapter or bc.get('adapter','hci0')
    radio=Radio(adapter,args.interval_ms);bridge=Bridge(args.drop_uplink_every,args.drop_result_every)
    loop=asyncio.get_running_loop()
    await radio.start()
    if args.check:
        print('Advertising API available. This does not prove RF throughput or simultaneous RX/TX.')
        await radio.close();return
    from bleak import BleakScanner
    scanner=BleakScanner(detection_callback=lambda d,a:bridge.receive(d.address,a.manufacturer_data.get(COMPANY,b''),a.rssi),
                         adapter=adapter,scanning_mode='active',bluez={'filters':{'DuplicateData':True}})
    # Remotes are non-scannable; active discovery also works on older BlueZ
    # without AdvertisementMonitor support needed by Bleak passive scanning.
    mqtt=bridge.mqtt=arscfg.mqtt_client('ars-adv16',clean_session=True)
    mqtt.max_queued_messages_set(2048)
    mqtt.will_set('ars/adv16/link',json.dumps({'online':False}),qos=1,retain=True)
    def subscribed(c,u,mid,qos,*extra):
        if mid==bridge.sub_mid and all(int(q)<128 for q in qos):
            loop.call_soon_threadsafe(setattr,bridge,'online',True)
            c.publish('ars/adv16/link',json.dumps({'online':True}),qos=1,retain=True)
    def connected(c,u,f,rc):
        if rc==0:
            _,bridge.sub_mid=c.subscribe([('ars/+/state',1),('ars/+/result/adv16',1)])
    def disconnected(c,u,rc):loop.call_soon_threadsafe(bridge.disconnected)
    def message(c,u,msg):loop.call_soon_threadsafe(bridge.message,msg.topic,bytes(msg.payload),bool(msg.retain))
    mqtt.on_connect=connected;mqtt.on_subscribe=subscribed;mqtt.on_disconnect=disconnected;mqtt.on_message=message
    mqtt.connect(cp['mqtt']['host'],int(cp['mqtt'].get('port',1883)),30);mqtt.loop_start()
    try:
        await scanner.start()
        log.info('ADV18 running: continuous discovery; downlink pulse=%sms RX-only gap=%sms; STATE at most once/s', args.page_ms,args.rx_gap_ms)
        last_status=0
        while True:
            data=bridge.page()
            if bridge.online and time.monotonic()-last_status>=5:
                for room in bridge.states:
                    mqtt.publish(f'ars/{room}/gw/status',json.dumps({'online':True,'port':'BLE ADV16 '+adapter}),qos=1,retain=False)
                last_status=time.monotonic()
            await transmit_page(radio,bridge,data,args.page_ms,args.rx_gap_ms)
    finally:
        with contextlib.suppress(Exception):await scanner.stop()
        await radio.close()
        mqtt.publish('ars/adv16/link',json.dumps({'online':False}),qos=1,retain=True)
        mqtt.disconnect();mqtt.loop_stop()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config');p.add_argument('--adapter');p.add_argument('--check',action='store_true')
    p.add_argument('--interval-ms',type=int,default=100)
    p.add_argument('--page-ms',type=int,default=220)
    p.add_argument('--rx-gap-ms',type=int,default=180)
    p.add_argument('--drop-uplink-every',type=int,default=0)
    p.add_argument('--drop-result-every',type=int,default=0)
    a=p.parse_args()
    if not (100<=a.interval_ms<=1000 and a.page_ms>=a.interval_ms+50 and a.page_ms<=2000):
        p.error('Require 100<=interval<=1000 and interval+50<=page<=2000 ms')
    if not 100<=a.rx_gap_ms<=2000:p.error('Require 100<=rx-gap-ms<=2000')
    if min(a.drop_uplink_every,a.drop_result_every)<0:p.error('drop counts must be >=0')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:asyncio.run(run(a))
    except KeyboardInterrupt:pass

if __name__=='__main__':main()
