#!/usr/bin/env python3
"""Capture Serial at 115200 or analyze an existing log; never generates answers.
Reports firmware transaction time (not BLE ping-only, not human reaction time).
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import statistics
import time
BEGIN=re.compile(r'ADV_BEGIN token=([0-9a-f]{16}) type=(\d+)')
END=re.compile(r'ADV_METRIC token=([0-9a-f]{16}) type=(\d+) status=(\d+) elapsed_ms=(\d+) attempts=(\d+)')

def analyze(text):
    starts={};ends={};conflicts=[]
    for line in text.splitlines():
        b=BEGIN.search(line);e=END.search(line)
        if b:starts[b[1]]=int(b[2])
        if e:
            row=dict(token=e[1],type=int(e[2]),status=int(e[3]),elapsed_ms=int(e[4]),attempts=int(e[5]))
            if e[1] in ends and ends[e[1]]!=row:conflicts.append(e[1])
            ends[e[1]]=row
    answers={k for k,v in starts.items() if v==2}
    rows=[ends[k] for k in answers if k in ends]
    accepted=[r['elapsed_ms'] for r in rows if r['status']==0]
    accepted.sort()
    report=dict(answer_starts=len(answers),accepted=sum(r['status']==0 for r in rows),
                outcomes=len(rows),retry_transactions=sum(r['attempts']>1 for r in rows),
                first_attempt_outcomes=sum(r['attempts']==1 for r in rows),
                rejected=sum(0<r['status']<=255 for r in rows),
                unknown=sum(r['status']>=256 for r in rows),incomplete_log_or_pending=len(answers)-len(rows),
                conflicting_metrics=conflicts,orphan_outcomes=len(set(ends)-set(starts)),
                latency_ms_accepted=dict(median=statistics.median(accepted),p95=accepted[math.ceil(.95*len(accepted))-1],max=max(accepted)) if accepted else None,
                note='Remote transaction duration through backend result. Not proof of 50-device RF capacity or zero false ACKs; compare DB and logs.')
    return report,sorted(rows,key=lambda r:r['token'])

def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--log',type=Path);g.add_argument('--port')
    p.add_argument('--drain-seconds',type=int,default=15)
    p.add_argument('--target-answers',type=int,default=0,help='Stop new sends after this many ANSWER starts; 0 uses time only')
    p.add_argument('--seconds',type=int,default=300);p.add_argument('--output',type=Path,default=Path('adv_demo'))
    a=p.parse_args()
    if a.seconds<1:p.error('--seconds must be positive')
    if a.target_answers<0:p.error('--target-answers must be >=0')
    if not 0<=a.drain_seconds<=60:p.error('--drain-seconds must be 0..60')
    if a.port:
        import serial
        lines=[];deadline=time.monotonic()+a.seconds;draining=False;seen=set();buffer=b''
        print('Open capture. Use a TEST classroom/question; press answers on remote. Ctrl+C stops capture.')
        with serial.Serial(a.port,115200,timeout=.2) as port, a.output.with_suffix('.log').open('w') as log:
            try:
                while time.monotonic()<deadline+a.drain_seconds:
                    if not draining and time.monotonic()>=deadline:
                        print('NGUNG BAM: dang cho ACK cuoi, khong gui dap an moi.',flush=True)
                        draining=True
                    buffer+=port.readline()
                    while b'\n' in buffer:
                        raw,buffer=buffer.split(b'\n',1)
                        line=raw.decode('utf-8','replace')+'\n'
                        stamp=datetime.now(timezone.utc).isoformat(timespec='milliseconds')
                        stamped=f'HOST_RX_UTC={stamp} {line}'
                        if not stamped.endswith('\n'):stamped+='\n'
                        lines.append(stamped);log.write(stamped);log.flush();print(stamped,end='',flush=True)
                        match=BEGIN.search(line)
                        if match and int(match[2])==2 and match[1] not in seen:
                            seen.add(match[1])
                            print(f'DA GUI {len(seen)}/{a.target_answers or "time-limited"}',flush=True)
                            if a.target_answers and len(seen)>=a.target_answers and not draining:
                                deadline=time.monotonic();draining=True
                                print('NGUNG BAM: da du so lan gui; dang cho phan hoi cuoi.',flush=True)
            except KeyboardInterrupt:pass
        text=''.join(lines)
    else:text=a.log.read_text(errors='replace')
    report,rows=analyze(text)
    report['target_answers']=a.target_answers
    report['target_reached']=bool(a.target_answers and report['answer_starts']>=a.target_answers)
    a.output.with_suffix('.json').write_text(json.dumps(report,indent=2))
    with a.output.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['token','type','status','elapsed_ms','attempts']);w.writeheader();w.writerows(rows)
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
