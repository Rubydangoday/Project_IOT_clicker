#!/usr/bin/env python3
"""V3.12 room-change lifecycle tests using real bridge code and fake transports."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'server'/'bridge'),str(ROOT/'server'/'common')]
import ble_gatt as bg
import gatt_protocol as gp
import blecodec


class FakeMQTT:
    def __init__(self, name):
        self.name=name;self.sent=[];self.subscriptions=[];self.disconnected=False;self.will=None
        self.rejected_rooms=set()
    def will_set(self,topic,payload,**kw):self.will=(topic,payload,kw)
    def connect_async(self,*a):pass
    def loop_start(self):self.on_connect(self,None,None,0)
    def loop_stop(self):pass
    def subscribe(self,topics):
        self.subscriptions=topics
        self.on_subscribe(self,None,1,[1]*len(topics))
    def disconnect(self):
        self.disconnected=True;self.on_disconnect(self,None,0)
    def deliver(self,topic,payload,retained=False):
        self.on_message(self,None,SimpleNamespace(topic=topic,payload=payload.encode(),retain=retained))
    def publish(self,topic,payload,**kw):
        self.sent.append((topic,payload,kw))
        if topic.endswith('/resp'):
            p=json.loads(payload)
            result={k:p[k] for k in ('room','mac','type','id','q','seq','ans','gatt_request')}
            result['status']=4 if p['room'] in self.rejected_rooms else 0
            self.deliver(f"ars/{p['room']}/result/gatt",json.dumps(result))
        return SimpleNamespace(rc=0,wait_for_publish=lambda timeout:None)


class FakePeripheral:
    def __init__(self, link, room):
        self.link=link;self.room=room;self.seat=2;self.is_connected=True;self.ready=False
        self.sent=[];self.seq=0
    def set_room(self,room):self.room=room;self.ready=False
    async def write_gatt_char(self,uuid,record,response):
        self.sent.append(record)
        payload=record[1:]
        if payload[1]==gp.HELLO:
            was_ready=self.ready;self.ready=payload[2]==self.room
            self.link.on_notify(None,gp.frame(bytes([0xA5,gp.HELLO_REPLY,self.room,self.seat])))
            if self.ready and not was_ready:
                self.seq+=1
                self.link.on_notify(None,gp.frame(blecodec.encode_uplink(1,self.room,self.seat,0,self.seq)))


class SwitchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients=[]
        def factory(name,**kw):
            c=FakeMQTT(name);self.clients.append(c);return c
        self.patch=patch.object(bg.arscfg,'mqtt_client',side_effect=factory);self.patch.start()
        self.link=bg.Link({'mqtt':{'host':'localhost','port':'1883'}},1)
        self.link.device_address='D4:10:20:56:14:F8'
        self.ble=FakePeripheral(self.link,4);self.link.client=self.ble
    async def asyncTearDown(self):
        await self.link.stop_mqtt();self.patch.stop()
    async def settle(self):
        for _ in range(4):await asyncio.sleep(0)
    async def bootstrap(self):
        discovered=await self.link.exchange_hello(0)
        self.assertEqual(discovered,self.ble.room)
        await self.link.select_room(discovered);await self.settle()

    async def test_bootstrap_uses_remote_room_not_config(self):
        await self.bootstrap()
        self.assertEqual(self.link.room,4);self.assertTrue(self.link.ready)
        self.assertTrue(self.ble.is_connected);self.assertFalse(self.link.lost.is_set())
        self.assertEqual(self.clients[0].will[0],'ars/4/gw/status')
        self.assertTrue(all(topic.startswith('ars/4/') for topic,_ in self.clients[0].subscriptions))
        responses=[json.loads(p) for t,p,k in self.clients[0].sent if t.endswith('/resp')]
        self.assertEqual(len(responses),1);self.assertEqual(responses[0]['type'],1)
        self.assertEqual((await self.link.queue.get())[2][1],gp.LOGIN_RESULT)

    async def test_room_changes_4_to_1_to_4_keep_ble_connected(self):
        await self.bootstrap()
        for room in (1,4):
            old=self.clients[-1];old_room=self.link.room
            self.ble.set_room(room)
            reported=await self.link.exchange_hello(old_room)
            self.assertFalse(self.link.ready)
            await self.link.select_room(reported);await self.settle()
            self.assertTrue(old.disconnected);self.assertTrue(self.ble.is_connected)
            self.assertFalse(self.link.lost.is_set());self.assertTrue(self.link.ready)
            self.assertEqual(self.link.room,room)
            statuses=[json.loads(p) for t,p,k in old.sent if t==f'ars/{old_room}/gw/status']
            self.assertFalse(statuses[-1]['online'])
            self.assertEqual(self.clients[-1].will[0],f'ars/{room}/gw/status')

    async def test_delayed_previous_client_callback_cannot_reach_new_room(self):
        await self.bootstrap();old=self.clients[-1]
        self.ble.set_room(1);await self.link.select_room(1);await self.settle()
        n=self.link.queue.qsize()
        # Includes an intentionally matching NEW topic from a retired client.
        old.deliver('ars/1/state',json.dumps({'cmds':['STATE 1 8 1 4 00']}))
        old.on_disconnect(old,None,1);await self.settle()
        self.assertEqual(n,self.link.queue.qsize());self.assertFalse(self.link.lost.is_set())
        self.assertTrue(self.link.mqtt_ready.is_set())

    async def test_wrong_room_state_is_ignored_even_if_topic_is_current(self):
        await self.bootstrap();n=self.link.queue.qsize()
        self.link.on_mqtt('ars/4/state',json.dumps({'cmds':['STATE 1 3 1 4 00']}).encode(),False)
        self.link.on_mqtt('ars/1/state',json.dumps({'cmds':['STATE 1 3 1 4 00']}).encode(),False)
        self.assertEqual(n,self.link.queue.qsize());self.assertEqual(self.link.snapshots,{})

    async def test_old_write_dequeued_before_switch_is_discarded(self):
        await self.bootstrap();old_generation=self.link.generation
        payload=bytes([0xA5,0x13,4,1,2,1,7,3,0])
        self.ble.set_room(1);await self.link.select_room(1)
        n=len(self.ble.sent)
        await self.link.write(payload,old_generation)
        self.assertEqual(n,len(self.ble.sent))

    async def test_switch_discards_snapshot_and_old_transaction_token(self):
        await self.bootstrap()
        p=self.link.txns.request(blecodec.encode_uplink(2,4,2,1,7,'A'))
        self.link.snapshots[0x10]=bytes([0xA5,0x10,4])
        self.ble.set_room(1);await self.link.select_room(1)
        self.ble.set_room(4);await self.link.select_room(4);await self.settle()
        self.assertEqual(self.link.snapshots,{})
        old={**{k:p[k] for k in ('room','mac','type','id','q','seq','ans','gatt_request')},'status':0}
        self.assertIsNone(self.link.txns.result(old))

    async def test_room_changed_again_during_subscription(self):
        original=self.link.start_mqtt
        async def changing_start():
            await original()
            if self.link.room==4:self.ble.set_room(7)
        self.link.start_mqtt=changing_start
        await self.link.select_room(4);await self.settle()
        self.assertEqual(self.link.room,7);self.assertTrue(self.link.ready)
        self.assertFalse(self.link.lost.is_set());self.assertTrue(self.ble.is_connected)

    async def test_no_session_nack_keeps_ble_alive(self):
        original=self.link.start_mqtt
        async def no_session():
            await original();self.link.mqtt.rejected_rooms.add(4)
        self.link.start_mqtt=no_session
        await self.bootstrap()
        result=(await self.link.queue.get())[2]
        self.assertEqual(result[-1],4);self.assertTrue(self.ble.is_connected)
        self.assertFalse(self.link.lost.is_set())

    async def test_connection_loss_during_hello_exits_immediately(self):
        self.link.lost.set()
        with self.assertRaises(ConnectionError):
            await asyncio.wait_for(self.link.wait_event(asyncio.Event(),5,'test'),0.1)

    async def test_invalid_remote_room_rejected(self):
        self.link.on_notify(None,gp.frame(bytes([0xA5,gp.HELLO_REPLY,0,2])))
        self.assertTrue(self.link.lost.is_set())

if __name__=='__main__':unittest.main(verbosity=2)
