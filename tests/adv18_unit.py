import json
from pathlib import Path
import struct
import sys
import unittest
import ctypes
import errno
import socket
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'server'/'bridge'), str(ROOT/'tools'), str(ROOT/'server'/'ingest'), str(ROOT/'server'/'common')]
from adv_phy import scan_1m_mask, decode_reply, Mgmt, bind_control, SockaddrHci
from verify_adv_trace import inspect_trace


def event(op, status=0, payload=b'', index=0, kind=1):
    p = struct.pack('<HB', op, status) + payload
    return struct.pack('<HHH', kind, index, len(p)) + p


def trace(phys=1, duplicate=1, status=0):
    params = bytes([1, 0, phys]) + bytes.fromhex('0112001200') * phys.bit_count()
    commands = [(2, struct.pack('<HB', 0x2041, len(params))+params),
                (3, bytes.fromhex('0e04014120')+bytes([status])),
                (2, bytes.fromhex('42200601')+bytes([duplicate])+bytes(4))]
    result = struct.pack('>8sII', b'btsnoop\0', 1, 2001)
    for kind, p in commands:
        result += struct.pack('>IIIIQ', len(p), len(p), kind, 0, 0)+p
    return result


class Checks(unittest.TestCase):
    def test_control_bind_abi_and_errno(self):
        def inspect(fd, pointer, size):
            addr = ctypes.cast(pointer, ctypes.POINTER(SockaddrHci)).contents
            self.assertEqual((fd, size), (42, 6))
            self.assertEqual((addr.family, addr.device, addr.channel),
                             (socket.AF_BLUETOOTH, 0xffff, 3))
            return 0
        libc = Mock()
        libc.bind.side_effect = inspect
        sock = Mock()
        sock.fileno.return_value = 42
        with patch('adv_phy.ctypes.CDLL', return_value=libc), \
                patch.object(socket, 'AF_BLUETOOTH', 31, create=True):
            bind_control(sock)
            libc.bind.side_effect = None
            libc.bind.return_value = -1
            ctypes.set_errno(errno.EPERM)
            with self.assertRaises(OSError) as ctx:bind_control(sock)
            self.assertEqual(ctx.exception.errno, errno.EPERM)

    def test_both_coded_bits_clear_preserving_others(self):
        self.assertEqual(scan_1m_mask(0x7fff, 0x79fe, 0x7fff), 0x1fff)
        self.assertEqual(scan_1m_mask(0x7fff, 0x79fe, 0x3fff), 0x1fff)
        self.assertEqual(scan_1m_mask(0x7fff, 0x79fe, 0x1fff), 0x1fff)

    def test_reject_unsupported_or_required_bit_change(self):
        for values in [(0x7fff, 0x3fff, 0x7fff), (0x7fff, 0x5fff, 0x7fff), (0x7fff, 0x7fff, 0x4000), (0x400, 0x400, 0x600)]:
            with self.assertRaises(RuntimeError):scan_1m_mask(*values)

    def test_reply_routing_errors_and_sizes(self):
        self.assertIsNone(decode_reply(event(0x44, index=1), 0, 0x44))
        self.assertIsNone(decode_reply(event(0x45), 0, 0x44))
        self.assertEqual(decode_reply(event(0x44, payload=b'123'), 0, 0x44), b'123')
        for data in [event(0x44, status=0x0c), event(0x44)[:-1], b'xx']:
            with self.assertRaises(RuntimeError):decode_reply(data, 0, 0x44)

    def test_set_checks_readback(self):
        client = object.__new__(Mgmt)
        sent = []
        client.command = lambda op, payload: sent.append((op, payload))
        client.snapshot = lambda: {'selected': 0x3fff}
        self.assertEqual(client.set(0x3fff), {'selected': 0x3fff})
        self.assertEqual(sent, [(0x45, struct.pack('<I', 0x3fff))])
        with self.assertRaises(RuntimeError):client.set(0x7fff)

    def test_trace_requires_single_phy_and_unchanged_duplicate_policy(self):
        self.assertTrue(inspect_trace(trace())['one_variable_test_verified'])
        for raw in [trace(5), trace(1, 0), trace(status=0x0c), trace()[:16]]:
            self.assertFalse(inspect_trace(raw)['one_variable_test_verified'])

    def test_trace_rejects_truncation(self):
        with self.assertRaises(ValueError):inspect_trace(trace()[:-1])


class Regression(unittest.TestCase):
    def test_service_restart_is_idempotent_and_preserves_backup(self):
        import contextlib
        import io
        import os
        import tempfile
        import adv_phy
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)/'phy.json';config=Path(td)/'config.ini'
            before=dict(index=0,address='A8:E2:91:E8:9D:C2',supported=0x7fff,configurable=0x79fe,selected=0x7fff)
            state.write_text(json.dumps(before));config.write_text('[ble]\nadapter=hci0\n')
            current=before.copy()
            client=Mock();client.snapshot.side_effect=lambda:current.copy()
            def set_phy(mask):current['selected']=mask;return current.copy()
            client.set.side_effect=set_phy
            with patch.object(adv_phy,'Mgmt',return_value=client), \
                    patch.object(adv_phy.os,'geteuid',return_value=0), \
                    patch.dict(os.environ, {'ARS_CONFIG':str(config)}), \
                    patch.object(sys,'argv',['adv_phy','ensure','--state',str(state)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                adv_phy.main();adv_phy.main()
            client.set.assert_called_once_with(0x1fff)
            self.assertEqual(json.loads(state.read_text()),before)

    def test_capture_stops_at_target_and_keeps_final_ack(self):
        import contextlib
        import io
        import tempfile
        from types import SimpleNamespace
        import adv_measure
        clock = [0.0]
        chunks = []
        for n in range(100):
            chunks.extend([f'ADV_BEGIN token={n:016x} '.encode(), b'type=2\n',
                           f'ADV_METRIC token={n:016x} type=2 status=0 elapsed_ms=600 attempts=1\n'.encode()])
        class Serial:
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def readline(self):
                clock[0] += .1
                return chunks.pop(0) if chunks else b''
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'remote'
            with patch.dict(sys.modules, {'serial':SimpleNamespace(Serial=Serial)}), \
                    patch.object(sys,'argv',['adv_measure','--port','fake','--seconds','600','--target-answers','100','--output',str(dest)]), \
                    patch.object(adv_measure.time,'monotonic',side_effect=lambda:clock[0]), \
                    contextlib.redirect_stdout(io.StringIO()):
                adv_measure.main()
            r=json.loads(dest.with_suffix('.json').read_text())
            self.assertTrue(r['target_reached'])
            self.assertEqual((r['answer_starts'],r['accepted'],r['incomplete_log_or_pending']),(100,100,0))
            self.assertLess(clock[0],60)

    def test_offline_gateway_query_formats_percent_as_parameter(self):
        import threading
        from types import SimpleNamespace
        from ingest_adv import AdvIngest
        instance = AdvIngest.__new__(AdvIngest)
        instance.lock = threading.Lock()
        formatted = []
        # Reproduce the DB driver's Python %-formatting stage, including empty args.
        def execute(sql, args=()):
            formatted.append(sql % tuple("'"+v.replace("'", "''")+"'" for v in args))
        instance.x = execute
        instance.on_message(None, None, SimpleNamespace(topic='ars/adv16/link',payload=b'{"online":false}'))
        self.assertEqual(formatted, ["UPDATE gateways SET online=0,updated_at=NOW() WHERE port LIKE 'BLE ADV16%'"])
        instance.on_message(None, None, SimpleNamespace(topic='ars/adv16/link',payload=b'{"online":true}'))
        self.assertEqual(len(formatted), 1)

    def test_capture_counts_rejection_retry_pending_and_duplicate_metric(self):
        from adv_measure import analyze
        text = """ADV_BEGIN token=0000000000000001 type=2
ADV_BEGIN token=0000000000000002 type=2
ADV_BEGIN token=0000000000000003 type=2
ADV_METRIC token=0000000000000001 type=2 status=0 elapsed_ms=600 attempts=2
ADV_METRIC token=0000000000000001 type=2 status=0 elapsed_ms=600 attempts=2
ADV_METRIC token=0000000000000002 type=2 status=2 elapsed_ms=500 attempts=1
"""
        r,_=analyze(text)
        self.assertEqual((r['answer_starts'],r['accepted'],r['rejected'],r['outcomes'],r['incomplete_log_or_pending'],r['retry_transactions']), (3,1,1,2,1,1))

if __name__ == '__main__':unittest.main(verbosity=2)
