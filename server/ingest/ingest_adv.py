#!/usr/bin/env python3
"""Advertising-only entrypoint; original GATT ingest remains untouched.
The response and the idempotency ledger commit in ONE MariaDB transaction.
Only committed results are published. A lost publish is recovered by remote retry.
"""
import argparse
import json
import logging
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from ingest import Ingest
import arscfg
from adv_protocol import validate, canonical
log=logging.getLogger('ingest-adv')


class AdvIngest(Ingest):
    def on_connect(self,client,userdata,flags,rc):
        super().on_connect(client,userdata,flags,rc)
        client.subscribe('ars/adv16/link',qos=1)

    def on_message(self,client,userdata,msg):
        if msg.topic=='ars/adv16/link':
            try:
                if not json.loads(msg.payload).get('online'):
                    with self.lock:
                        self.x("UPDATE gateways SET online=0,updated_at=NOW() WHERE port LIKE %s",
                               ('BLE ADV16%',))
            except Exception:log.exception('ADV gateway status update failed')
            return
        super().on_message(client,userdata,msg)

    def publish_gatt_result(self,pkt,status=0):
        # Base business rules call this on every definitive outcome. Stage only.
        self._adv_status=int(status)

    def remember_ack(self,*args):pass
    def remember_reject_result(self,*args):pass
    def drop_ack(self,*args):pass

    def q(self,sql,args=(),one=False):
        # The persistent ledger replaces the legacy 8-bit, 10-second heuristic.
        if sql.startswith('SELECT answer FROM responses WHERE session_q_id='):
            return None
        if sql.startswith('SELECT s.*, c.conn_mode FROM sessions s JOIN classes c'):
            sql=sql.replace('ORDER BY s.id DESC LIMIT 1','AND s.id=%s ORDER BY s.id DESC LIMIT 1')
            args=(*args,self._adv_session)
        return super().q(sql,args,one)

    def emit(self,pkt,status):
        result={k:pkt[k] for k in ('mac','room','type','id','q','seq','ans','adv_session','adv_token')}
        result['status']=status
        info=self.client.publish(f"ars/{pkt['room']}/result/adv16",json.dumps(result),qos=1,retain=False)
        if info.rc:log.warning('Result MQTT enqueue failed token=%s rc=%s',pkt['adv_token'],info.rc)

    def process(self,pkt,raw):
        try: validate(pkt)
        except (ValueError,KeyError,TypeError):
            log.warning('Ignored non-ADV16 or malformed request');return
        request=canonical(pkt)
        self._adv_status=None;self._adv_session=pkt['adv_session']
        self.db.begin()
        try:
            prior=super().q('SELECT request_json,status FROM adv_transactions WHERE mac=%s AND token=%s FOR UPDATE',
                            (pkt['mac'],pkt['adv_token']),one=True)
            if prior:
                if prior['request_json']!=request or prior['status'] is None:
                    raise ValueError('token collision or incomplete ledger; no ACK')
                status=int(prior['status'])
            else:
                self.x('INSERT INTO adv_transactions (mac,token,request_json) VALUES (%s,%s,%s)',
                       (pkt['mac'],pkt['adv_token'],request))
                super().process(pkt,raw)
                if self._adv_status is None:raise RuntimeError('business rules returned no result')
                status=self._adv_status
                self.x('UPDATE adv_transactions SET status=%s WHERE mac=%s AND token=%s',
                       (status,pkt['mac'],pkt['adv_token']))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        log.info('ADV COMMIT token=%s type=%s seat=%s q=%s status=%s cached=%s',
                 pkt['adv_token'],pkt['type'],pkt['id'],pkt['q'],status,bool(prior))
        self.emit(pkt,status)


def initialize(cp):
    db=arscfg.db_connect(cp)
    try:
        with db.cursor() as c:
            c.execute((Path(__file__).resolve().parents[1]/'db/migrate_013_adv_transactions.sql').read_text())
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--init-db',action='store_true')
    a=p.parse_args();cp=arscfg.load(a.config)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if a.init_db:initialize(cp)
    else:
        server=AdvIngest(cp)
        server.q('SELECT token FROM adv_transactions LIMIT 1') # fail loudly if migration missing
        server.run()
