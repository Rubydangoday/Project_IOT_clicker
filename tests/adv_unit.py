#!/usr/bin/env python3
"""Offline protocol, scheduler, real business-rule + transactional ledger tests.
SQLite supplies real commit/rollback persistence; SQL adapter is test-only.
Run MariaDB integration on target before claiming engine-specific validation.
"""
import asyncio
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'server'/'bridge'),str(ROOT/'server'/'ingest'),str(ROOT/'server'/'common')]
import adv_protocol as ap
from ble_adv import Bridge, transmit_page
from ingest_adv import AdvIngest


def packet(i=1,typ=2):
 return dict(mac=f'D4:10:20:56:14:{i:02X}',room=1,type=typ,id=i,q=1 if typ==2 else 0,
             seq=1,ans='B' if typ==2 else '',adv_session=1,adv_token=f'{i+typ*1000:016x}',
             via='ble',transport='adv16',batt=None,rssi=-65)
class MQTT:
 def __init__(self):self.sent=[]
 def publish(self,t,p,**kw):self.sent.append((t,json.loads(p),kw));return SimpleNamespace(rc=0)

class Protocol(unittest.TestCase):
 def test_roundtrip_size_and_reject(self):
  for typ in (1,2):
   p=packet(1,typ);self.assertEqual(ap.decode(ap.encode(p),p['mac'],-65),p)
   self.assertLessEqual(len(ap.encode(p))+4+3,31)
  for raw in (b'',b'\xa5'*21,ap.encode(packet())[:-1]):
   with self.assertRaises(ValueError):ap.decode(raw,packet()['mac'])
 def test_50_results_fair_and_not_evicted_by_retries(self):
  q=ap.ResultQueue()
  for i in range(50):q.put(1,f'{i+1:016x}',0,0)
  seen=set()
  for slot in range(25):
   q.put(1,f'{1:016x}',0,slot*.18) # hot retry cannot jump ahead
   page=q.page(slot*.18);self.assertLessEqual(len(page)+4+3,31)
   for pos in range(page[3]):seen.add(page[4+pos*9:12+pos*9].hex())
  self.assertEqual(len(seen),50);self.assertEqual(len(q.items),50)
 def test_capacity_expiry(self):
  q=ap.ResultQueue(capacity=2,ttl=5)
  q.put(1,'01'*8,0,0);q.put(1,'02'*8,0,0)
  with self.assertRaises(OverflowError):q.put(1,'03'*8,0,1)
  self.assertIsNone(q.page(6))

class BridgeTests(unittest.TestCase):
 def make(self,**kw):
  b=Bridge(**kw);b.mqtt=MQTT();b.online=True;return b
 def test_dedup_and_retry_forwarding(self):
  b=self.make();p=packet()
  for t in [0,.02,.1,.2,.5]:b.receive(p['mac'],ap.encode(p),-65,t)
  self.assertEqual(len(b.mqtt.sent),1)
  b.receive(p['mac'],ap.encode(p),-65,3);self.assertEqual(len(b.mqtt.sent),2)
 def test_exact_results_only(self):
  b=self.make();p=packet();b.receive(p['mac'],ap.encode(p),-65,0)
  good={**p,'status':0}
  for key,val in [('id',3),('ans','C'),('adv_session',2),('adv_token','00'*8),('q',2)]:
   b.message('ars/1/result/adv16',json.dumps({**good,key:val}),now=1)
  b.message('ars/1/result/adv16',json.dumps(good),True,now=1)
  self.assertFalse(b.results.items)
  b.message('ars/1/result/adv16',json.dumps(good),now=1);self.assertEqual(len(b.results.items),1)
 def test_stale_state_and_broker_loss(self):
  b=self.make();s=dict(room=1,qid=1,open=1,n_options=4,session_id=1,ts=0)
  b.message('ars/1/state',json.dumps(s),True,now=0,wall=30);self.assertIsNone(b.page(0))
  b.message('ars/1/state',json.dumps(s),True,now=0,wall=0);self.assertIsNotNone(b.page(0))
  self.assertIsNone(b.page(16));b.disconnected();self.assertFalse(b.online)
 def test_new_transaction_retires_only_same_devices_old_ack(self):
  b=self.make();first=packet();other=packet(2)
  for p in [first,other]:
   b.receive(p['mac'],ap.encode(p),-65,0)
   b.message('ars/1/result/adv16',json.dumps({**p,'status':0}),now=1)
  fresh={**first,'adv_token':'ab'*8};b.receive(fresh['mac'],ap.encode(fresh),-65,2)
  self.assertEqual(len(b.results.items),1)
  b.message('ars/1/result/adv16',json.dumps({**first,'status':0}),now=3)
  self.assertEqual(len(b.results.items),1)
 def test_fault_injection_drops_first_burst_and_first_result(self):
  b=self.make(drop_up=1,drop_result=1);p=packet()
  for t in [0,.1,.2]:b.receive(p['mac'],ap.encode(p),-65,t)
  self.assertFalse(b.mqtt.sent)
  b.receive(p['mac'],ap.encode(p),-65,3);self.assertEqual(len(b.mqtt.sent),1)
  msg=json.dumps({**p,'status':0})
  b.message('ars/1/result/adv16',msg,now=3);self.assertFalse(b.results.items)
  b.message('ars/1/result/adv16',msg,now=6);self.assertTrue(b.results.items)
 def test_50_results_plus_state_do_not_starve(self):
  b=self.make();s=dict(room=1,qid=1,open=1,n_options=4,session_id=1,ts=0)
  b.message('ars/1/state',json.dumps(s),now=0,wall=0)
  for i in range(1,51):
   p=packet(i);b.receive(p['mac'],ap.encode(p),-65,0)
   b.message('ars/1/result/adv16',json.dumps({**p,'status':0}),now=.1)
  seen=set();state_slots=0
  for slot in range(40):
   page=b.page(slot*.4)
   if page[1]==ap.STATE:state_slots+=1
   else:
    for n in range(page[3]):seen.add(page[4+9*n:12+9*n].hex())
  self.assertEqual(len(seen),50);self.assertGreaterEqual(state_slots,5)

 def test_idle_state_is_not_continuously_advertised(self):
  b=self.make();s=dict(room=1,qid=1,open=1,n_options=4,session_id=1,ts=0)
  b.message('ars/1/state',json.dumps(s),now=0,wall=0)
  self.assertIsNotNone(b.page(0))
  for t in [.02,.22,.4,.8,.99]:self.assertIsNone(b.page(t))
  self.assertIsNotNone(b.page(1))
  b.disconnected();self.assertIsNone(b.page(1.1))
 def test_downlink_pulse_is_followed_by_receive_only_gap(self):
  events=[]
  class Radio:
   async def show(self,data):events.append(('show',data))
   async def clear(self):events.append(('clear',))
  class Observer:
   def page_registered(self,data):events.append(('registered',data))
  async def wait(seconds):events.append(('wait',seconds))
  asyncio.run(transmit_page(Radio(),Observer(),b'page',220,180,wait))
  self.assertEqual(events,[('show',b'page'),('registered',b'page'),('wait',.22),('clear',),('wait',.18)])
  events.clear()
  asyncio.run(transmit_page(Radio(),Observer(),None,220,180,wait))
  self.assertEqual(events,[('show',None),('wait',.02)])

# Adapt only database syntax, not production business logic.
class Cursor:
 def __init__(self,db):self.db=db;self.cur=db.conn.cursor()
 def __enter__(self):return self
 def __exit__(self,*a):self.cur.close()
 def execute(self,sql,args=()):
  if self.db.fail_on and self.db.fail_on in sql:raise RuntimeError('injected DB failure')
  sql=sql.replace(' FOR UPDATE','').replace('%s','?').replace('NOW(3)',"'2026-10-14 12:00:00.000'").replace('NOW()',"'2026-10-14 12:00:00'")
  if 'ON DUPLICATE KEY UPDATE' in sql:
   sql=sql.split('ON DUPLICATE KEY UPDATE')[0]+' ON CONFLICT(mac) DO UPDATE SET pkt_total=pkt_total+1'
  self.cur.execute(sql,args);return self.cur.rowcount
 def fetchone(self):
  r=self.cur.fetchone();return dict(r) if r else None
 def fetchall(self):return [dict(r) for r in self.cur.fetchall()]
class DB:
 def __init__(self,path):
  self.conn=sqlite3.connect(path,isolation_level=None);self.conn.row_factory=sqlite3.Row;self.fail_on=None;self.fail_commit=False
 def cursor(self):return Cursor(self)
 def begin(self):self.conn.execute('BEGIN')
 def commit(self):
  if self.fail_commit:raise RuntimeError('injected commit failure')
  self.conn.commit()
 def rollback(self):self.conn.rollback()

def schema(db):
 db.conn.executescript('''
 CREATE TABLE classes(id INTEGER PRIMARY KEY,room_id INT,conn_mode TEXT);
 CREATE TABLE sessions(id INTEGER PRIMARY KEY,class_id INT,status TEXT,set_id INT,allow_change INT);
 CREATE TABLE students(class_id INT,seat_no INT);
 CREATE TABLE device_mappings(class_id INT,seat_no INT,mac TEXT);
 CREATE TABLE session_logins(session_id INT,seat_no INT,mac TEXT,logged_at TEXT,UNIQUE(session_id,seat_no));
 CREATE TABLE questions(id INTEGER PRIMARY KEY,n_options INT,position INT,set_id INT);
 CREATE TABLE session_questions(id INTEGER PRIMARY KEY,session_id INT,question_id INT,status TEXT,deadline TEXT);
 CREATE TABLE responses(id INTEGER PRIMARY KEY,session_q_id INT,seat_no INT,mac TEXT,seq INT,answer TEXT,rssi INT,received_at TEXT);
 CREATE TABLE devices(mac TEXT PRIMARY KEY,last_seen TEXT,last_batt_mv INT,last_rssi INT,last_room INT,last_via TEXT,pkt_total INT,pkt_dup INT DEFAULT 0,last_seat INT);
 CREATE TABLE rejected(received_at TEXT,room_id INT,session_id INT,mac TEXT,pkt_type INT,seat_no INT,qid INT,answer TEXT,reason TEXT,raw TEXT);
 CREATE TABLE adv_transactions(mac TEXT,token TEXT,request_json TEXT,status INT,PRIMARY KEY(mac,token));
 INSERT INTO classes VALUES(1,1,'ble');INSERT INTO sessions VALUES(1,1,'running',1,1);
 INSERT INTO questions VALUES(1,4,1,1);INSERT INTO session_questions VALUES(1,1,1,'open',NULL);
 ''')
 db.conn.executemany('INSERT INTO students VALUES(1,?)',[(i,) for i in range(1,51)])
def server(db):
 i=AdvIngest.__new__(AdvIngest);i.db=db;i.client=MQTT();i.stats={'ok':0,'dup':0,'rej':0}
 i.dirty=set();i.recent_rej={};i.lock=threading.Lock();return i
class Backend(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'db.sqlite';self.db=DB(self.path);schema(self.db);self.i=server(self.db)
 def tearDown(self):self.db.conn.close();self.temp.cleanup()
 def send(self,p):self.i.process(p,json.dumps(p))
 def count(self,table):return self.db.conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
 def test_login_answer_retry_restart_and_closed_question(self):
  self.send(packet(1,1));p=packet();self.send(p);self.send(p)
  self.assertEqual(self.count('responses'),1)
  self.db.conn.close();self.db=DB(self.path);self.i=server(self.db)
  self.db.conn.execute("UPDATE session_questions SET status='closed'")
  self.send(p);self.assertEqual(self.i.client.sent[-1][1]['status'],0);self.assertEqual(self.count('responses'),1)
  self.send({**p,'adv_token':'a1'*8});self.assertEqual(self.i.client.sent[-1][1]['status'],2)
 def test_new_token_same_seq_answer_is_new_transaction(self):
  self.send(packet(1,1));self.send(packet());self.send({**packet(),'adv_token':'b2'*8})
  self.assertEqual(self.count('responses'),2)
 def test_rollback_before_ledger_commit_and_retry(self):
  self.send(packet(1,1));sent=len(self.i.client.sent)
  self.db.fail_on='UPDATE adv_transactions SET status'
  with self.assertRaises(RuntimeError):self.send(packet())
  self.assertEqual(self.count('responses'),0);self.assertEqual(self.count('adv_transactions'),1)
  self.assertEqual(len(self.i.client.sent),sent)
  self.db.fail_on=None;self.send(packet());self.assertEqual(self.count('responses'),1)
 def test_commit_failure_does_not_ack(self):
  self.send(packet(1,1));sent=len(self.i.client.sent);self.db.fail_commit=True
  with self.assertRaises(RuntimeError):self.send(packet())
  self.assertEqual(len(self.i.client.sent),sent);self.assertEqual(self.count('responses'),0)
 def test_committed_answer_survives_result_publish_failure(self):
  self.send(packet(1,1));client=self.i.client
  def failed_publish(*args,**kw):
   self.assertFalse(self.db.conn.in_transaction)
   raise RuntimeError('MQTT lost after commit')
  self.i.client=SimpleNamespace(publish=failed_publish)
  with self.assertRaises(RuntimeError):self.send(packet())
  self.assertEqual(self.count('responses'),1)
  self.i=server(self.db);self.send(packet())
  self.assertEqual(self.count('responses'),1);self.assertEqual(self.i.client.sent[-1][1]['status'],0)
 def test_token_conflict_no_ack_no_mutation(self):
  self.send(packet(1,1));self.send(packet());sent=len(self.i.client.sent)
  with self.assertRaises(ValueError):self.send({**packet(),'ans':'C'})
  self.assertEqual(len(self.i.client.sent),sent);self.assertEqual(self.count('responses'),1)
 def test_old_session_and_unknown_seat_nack(self):
  self.send({**packet(1,1),'adv_session':2});self.assertEqual(self.i.client.sent[-1][1]['status'],4)
  self.send(packet(60,1));self.assertEqual(self.i.client.sent[-1][1]['status'],8)
 def test_50_virtual_devices_repeated_answer(self):
  for i in range(1,51):self.send(packet(i,1))
  for repeat in range(5):
   for i in range(1,51):self.send(packet(i))
  self.assertEqual(self.count('responses'),50);self.assertEqual(self.count('adv_transactions'),100)
  self.assertTrue(all(p['status']==0 and not kw['retain'] for t,p,kw in self.i.client.sent))

if __name__=='__main__':unittest.main(verbosity=2)
