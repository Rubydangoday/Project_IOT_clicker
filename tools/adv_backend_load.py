#!/usr/bin/env python3
"""50 virtual identities over MQTT, NOT an RF/advertising benchmark.
Requires a dedicated running class named ADV16_TEST..., with seats 1..N.
Creates actual LOGIN/ANSWER records in that test session; no automatic cleanup.
"""
import argparse
import json
from pathlib import Path
import secrets
import sys
import threading
import time
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'server'/'common'),str(Path(__file__).resolve().parents[1]/'server'/'bridge')]
import arscfg
from adv_protocol import canonical

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config');p.add_argument('--test-session',type=int,required=True)
    p.add_argument('--room',type=int,required=True);p.add_argument('--question',type=int,required=True)
    p.add_argument('--devices',type=int,default=50);p.add_argument('--copies',type=int,default=3)
    a=p.parse_args()
    if not 1<=a.devices<=50 or not 1<=a.copies<=10:p.error('devices 1..50, copies 1..10')
    cp=arscfg.load(a.config);db=arscfg.db_connect(cp)
    try:
        with db.cursor() as c:
            c.execute('SELECT s.id,c.name FROM sessions s JOIN classes c ON c.id=s.class_id WHERE s.id=%s AND c.room_id=%s AND s.status="running"',(a.test_session,a.room))
            row=c.fetchone()
            if not row or not row['name'].startswith('ADV16_TEST'):
                raise SystemExit('Refused: use a running TEST class named ADV16_TEST... with a test question')
    finally:db.close()
    ready=threading.Event();received={};expected={};lock=threading.Lock()
    cli=arscfg.mqtt_client('ars-adv16-test-'+secrets.token_hex(4),clean_session=True)
    def connect(c,u,f,rc):
        if rc==0:c.subscribe(f'ars/{a.room}/result/adv16',qos=1)
    def subscribed(c,u,mid,qos):
        if all(int(q)<128 for q in qos):ready.set()
    def message(c,u,msg):
        if msg.retain:return
        try:
            obj=json.loads(msg.payload);token=obj['adv_token']
            with lock:
                if token in expected and canonical(obj)==canonical(expected[token]):
                    received.setdefault(token,dict(status=obj['status'],elapsed_ms=round((time.monotonic()-expected[token]['started'])*1000,1)))
        except (KeyError,ValueError,TypeError):pass
    cli.on_connect=connect;cli.on_subscribe=subscribed;cli.on_message=message
    cli.connect(cp['mqtt']['host'],int(cp['mqtt'].get('port',1883)),30);cli.loop_start()
    try:
        if not ready.wait(5):raise SystemExit('MQTT subscription not ready')
        for typ in [1,2]:
            batch=[]
            with lock:
                for i in range(1,a.devices+1):
                    req=dict(mac=f'C2:16:00:00:00:{i:02X}',room=a.room,id=i,type=typ,q=a.question if typ==2 else 0,
                             seq=typ,ans='A' if typ==2 else '',batt=None,rssi=None,transport='adv16',via='ble',
                             adv_session=a.test_session,adv_token=secrets.token_hex(8),started=time.monotonic())
                    expected[req['adv_token']]=req;batch.append(req)
            for _ in range(a.copies):
                for req in batch:cli.publish(f'ars/{a.room}/resp',json.dumps(req),qos=1)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                with lock:pending=[r for r in batch if r['adv_token'] not in received]
                if not pending:break
                time.sleep(.5)
                for req in pending:cli.publish(f'ars/{a.room}/resp',json.dumps(req),qos=1)
            with lock:results=[received.get(r['adv_token'],{'status':'unknown'}) for r in batch]
            print(json.dumps(dict(test='MQTT/backend only, no RF',type=typ,devices=a.devices,results=results),indent=2))
            if any(r['status']!=0 for r in results):
                raise SystemExit('Stopped after NACK/missing result. Check test seats, mappings, session and open question.')
    finally:cli.disconnect();cli.loop_stop()
if __name__=='__main__':main()
