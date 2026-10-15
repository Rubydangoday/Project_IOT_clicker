"""V3.16 experimental connectionless protocol. No BLE/MQTT dependencies.

Manufacturer payload (company ID excluded), all integers little endian:
UPLINK 21 B: A6,type,room,seat,q,seq,answer,battery:u16,session:u32,token:8B
STATE  10 B: A6,30,room,q,open,options,session:u32
RESULT 22 B max: A6,31,room,count + <=2 (token:8B,status:u8)
Tokens are random per NEW transaction, immutable for retries; not authentication.
"""
from collections import OrderedDict
import json
import re
import struct

MAGIC, COMPANY, STATE, RESULT = 0xA6, 0xFFFF, 0x30, 0x31
LETTERS = 'ABCDEFGHIJ'
UP = struct.Struct('<7BHI8s')


def canonical(p):
    return json.dumps({k:p[k] for k in ('mac','room','type','id','q','seq','ans','adv_session','adv_token')},
                      sort_keys=True, separators=(',', ':'))


def validate(p):
    if p.get('transport') != 'adv16': raise ValueError('wrong transport')
    if not re.fullmatch(r'[0-9A-F]{2}(?::[0-9A-F]{2}){5}', p['mac']): raise ValueError('MAC')
    if not re.fullmatch(r'[0-9a-f]{16}', p['adv_token']) or int(p['adv_token'],16)==0: raise ValueError('token')
    if not (1<=p['room']<=99 and 1<=p['id']<=99 and 0<=p['seq']<=255
            and 1<=p['adv_session']<=0xffffffff): raise ValueError('identity')
    if p['type']==1 and p['q']==0 and p['ans']=='': return
    if p['type']==2 and 1<=p['q']<=99 and p['ans'] in LETTERS and len(p['ans'])==1: return
    raise ValueError('payload')


def decode(data, mac, rssi=None):
    if len(data)!=UP.size: raise ValueError('length')
    magic,typ,room,seat,q,seq,a,batt,session,token=UP.unpack(data)
    if magic!=MAGIC or a>10: raise ValueError('magic/answer')
    p=dict(mac=mac.upper(),type=typ,room=room,id=seat,q=q,seq=seq,
           ans=LETTERS[a-1] if a else '',batt=batt or None,rssi=rssi,via='ble',
           transport='adv16',adv_session=session,adv_token=token.hex())
    validate(p)
    return p


def encode(p):
    validate(p)
    return UP.pack(MAGIC,p['type'],p['room'],p['id'],p['q'],p['seq'],
                   LETTERS.index(p['ans'])+1 if p['ans'] else 0,p.get('batt') or 0,
                   p['adv_session'],bytes.fromhex(p['adv_token']))


def state_frame(s):
    room,q,op,n,sid=(int(s[k] or 0) for k in ('room','qid','open','n_options','session_id'))
    if not (1<=room<=99 and 0<=q<=99 and op in (0,1) and 0<=n<=10 and 0<=sid<=0xffffffff):
        raise ValueError('state')
    return struct.pack('<6BI',MAGIC,STATE,room,q,op,n,sid)


class ResultQueue:
    """Bounded fair carousel, NOT last-four-wins. Two records per radio frame.
    Retried records extend TTL without jumping ahead of other devices.
    """
    def __init__(self, capacity=512, ttl=20):
        self.items=OrderedDict();self.capacity=capacity;self.ttl=ttl

    def expire(self,now):
        for k in list(self.items):
            if self.items[k][1]<=now: del self.items[k]

    def put(self,room,token,status,now):
        self.expire(now);key=(room,token)
        if key not in self.items and len(self.items)>=self.capacity:
            raise OverflowError('ACK queue full; no old result silently evicted')
        self.items[key]=(status,now+self.ttl)

    def page(self,now):
        self.expire(now)
        if not self.items:return None
        first=next(iter(self.items));room=first[0]
        keys=[k for k in self.items if k[0]==room][:2]
        data=bytes([MAGIC,RESULT,room,len(keys)])
        for key in keys:
            data+=bytes.fromhex(key[1])+bytes([self.items[key][0]])
            self.items.move_to_end(key)
        return data
