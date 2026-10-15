#!/usr/bin/env python3
"""Linux Bluetooth MGMT PHY experiment. No raw HCI commands; standard library only."""
import argparse
import configparser
import ctypes
import json
import os
from pathlib import Path
import socket
import struct
import time

READ_INFO, GET_PHY, SET_PHY = 0x0004, 0x0044, 0x0045
CODED_RX, ONE_M_RX = 1 << 14, 1 << 10
CODED_MASK = (1 << 13) | CODED_RX


class SockaddrHci(ctypes.Structure):
    _fields_ = [('family', ctypes.c_ushort), ('device', ctypes.c_ushort),
                ('channel', ctypes.c_ushort)]


def bind_control(sock):
    # Python <=3.13 does not expose hci_channel in socket.bind().
    # Bind the existing socket through libc, using Linux's sockaddr_hci ABI.
    libc = ctypes.CDLL(None, use_errno=True)
    bind = libc.bind
    bind.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    bind.restype = ctypes.c_int
    addr = SockaddrHci(socket.AF_BLUETOOTH, 0xffff, 3)
    if bind(sock.fileno(), ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def scan_1m_mask(supported, configurable, selected):
    if not selected & ONE_M_RX:
        raise RuntimeError('LE 1M RX is not selected; refusing to guess adapter configuration')
    if selected & CODED_MASK & ~configurable:
        raise RuntimeError('LE Coded TX/RX cannot be deselected on this adapter')
    # Linux scan_coded() checks TX OR RX. Clearing RX alone leaves Coded scanning enabled.
    result = selected & ~CODED_MASK
    if result & ~supported:
        raise RuntimeError('Selected PHY mask contains unsupported bits')
    return result


def decode_reply(data, index, opcode):
    if len(data) < 6:
        raise RuntimeError('Truncated MGMT header')
    event, idx, size = struct.unpack_from('<HHH', data)
    if size != len(data) - 6:
        raise RuntimeError('Invalid MGMT packet length')
    if idx != index or event not in (0x0001, 0x0002):
        return None
    if size < 3:
        raise RuntimeError('Truncated MGMT command result')
    op, status = struct.unpack_from('<HB', data, 6)
    if op != opcode:
        return None
    if status:
        raise RuntimeError(f'MGMT opcode 0x{opcode:04x} failed: status=0x{status:02x}')
    if event == 0x0002:
        return None  # successful status is not the command-complete payload
    return data[9:]


class Mgmt:
    def __init__(self, index):
        self.index = index
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
        try:
            bind_control(self.sock)
        except Exception:
            self.sock.close()
            raise

    def command(self, opcode, payload=b''):
        packet = struct.pack('<HHH', opcode, self.index, len(payload)) + payload
        if self.sock.send(packet) != len(packet):
            raise RuntimeError('Short MGMT command write')
        deadline = time.monotonic() + 5
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'MGMT opcode 0x{opcode:04x} timed out')
            self.sock.settimeout(remaining)
            result = decode_reply(self.sock.recv(65535), self.index, opcode)
            if result is not None:
                return result

    def snapshot(self):
        info = self.command(READ_INFO)
        phy = self.command(GET_PHY)
        if len(info) < 6 or len(phy) != 12:
            raise RuntimeError('Unexpected controller/PHY response')
        supported, configurable, selected = struct.unpack('<III', phy)
        return dict(index=self.index, address=':'.join(f'{v:02X}' for v in info[:6][::-1]),
                    supported=supported, configurable=configurable, selected=selected)

    def set(self, selected):
        self.command(SET_PHY, struct.pack('<I', selected))
        actual = self.snapshot()
        if actual['selected'] != selected:
            raise RuntimeError(f'PHY readback mismatch: requested {selected:#x}, actual {actual["selected"]:#x}')
        return actual


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['save', 'apply', 'ensure', 'restore'])
    p.add_argument('--index', type=int, default=0)
    p.add_argument('--state', type=Path, required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        p.error('Run this helper with sudo')
    if not 0 <= a.index < 65535:
        p.error('Invalid adapter index')
    if a.action == 'ensure':
        cp = configparser.ConfigParser(inline_comment_prefixes=(';', '#'))
        config = os.environ.get('ARS_CONFIG', str(Path(__file__).resolve().parents[1] / 'config.ini'))
        if not cp.read(config) or cp.get('ble', 'adapter', fallback='hci0') != f'hci{a.index}':
            p.error('Runtime config adapter differs from PHY setup; inspect ADV18 installation')
    client = Mgmt(a.index)
    try:
        current = client.snapshot()
        if a.action == 'save':
            with a.state.open('x') as f:
                json.dump(current, f, indent=2)
                f.flush(); os.fsync(f.fileno())
            print(json.dumps(current)); return
        before = json.loads(a.state.read_text())
        if (before['index'], before['address']) != (current['index'], current['address']):
            raise RuntimeError('Adapter identity differs from backup; refusing to modify it')
        if a.action in ('apply', 'ensure'):
            if a.action == 'apply' and before['selected'] != current['selected']:
                raise RuntimeError('PHY configuration changed since backup; stop and inspect')
            target = scan_1m_mask(current['supported'], current['configurable'], current['selected'])
            if a.action == 'apply' and target == current['selected']:
                raise RuntimeError('LE Coded TX/RX were already disabled; this would not test a new condition')
        else:
            target = before['selected']
        result = client.set(target) if target != current['selected'] else current
        print(json.dumps(result))
        if a.action == 'ensure':
            print('ADV18 PHY readback OK: Coded TX/RX disabled; confirm scan PHY with HCI trace', flush=True)
    finally:
        client.sock.close()


if __name__ == '__main__':
    main()
