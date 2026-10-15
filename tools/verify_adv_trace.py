#!/usr/bin/env python3
"""Verify requested scan PHY and duplicate policy from Linux monitor btsnoop."""
import argparse
import json
from pathlib import Path
import struct


def inspect_trace(raw, index=0):
    if raw[:16] != struct.pack('>8sII', b'btsnoop\0', 1, 2001):
        raise ValueError('Expected Linux monitor btsnoop format 2001')
    pos = 16; phys = []; duplicates = []; errors = []
    while pos < len(raw):
        if len(raw) - pos < 24:
            raise ValueError('Truncated btsnoop record header')
        orig, size, flags, drops, stamp = struct.unpack_from('>IIIIQ', raw, pos)
        pos += 24
        data = raw[pos:pos + size]; pos += size
        if len(data) != size or orig != size:
            raise ValueError('Truncated btsnoop payload')
        if flags >> 16 != index:
            continue
        kind = flags & 65535
        if kind == 2:
            if len(data) < 3 or data[2] != len(data)-3:
                raise ValueError('Invalid HCI command length')
            op = int.from_bytes(data[:2], 'little'); p = data[3:]
            if op == 0x2041:
                if len(p) < 3 or len(p) != 3 + 5 * p[2].bit_count():
                    raise ValueError('Invalid extended scan parameters')
                phys.append(p[2])
            elif op == 0x200b:
                phys.append(1)  # legacy scan is LE 1M only
            elif op in (0x2042, 0x200c) and p and p[0] == 1:
                duplicates.append(p[1])
        elif kind == 3 and len(data) >= 6:
            if data[0] == 0x0e:
                op = int.from_bytes(data[3:5], 'little'); status = data[5]
            elif data[0] == 0x0f:
                op = int.from_bytes(data[4:6], 'little'); status = data[2]
            else:
                continue
            if op in (0x2041, 0x2042, 0x200b, 0x200c) and status:
                errors.append(dict(opcode=hex(op), status=status))
    passed = bool(phys) and all(v == 1 for v in phys) and bool(duplicates) and all(v == 1 for v in duplicates) and not errors
    return dict(scan_phy_masks=phys, enabled_scan_duplicate_filters=duplicates,
                scan_command_errors=errors, one_variable_test_verified=passed,
                note='PASS requires LE 1M only and duplicate filtering still enabled, as in baseline. HCI settings do not prove RF delivery.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path);p.add_argument('--index', type=int, default=0)
    a = p.parse_args()
    result = inspect_trace(a.trace.read_bytes(), a.index)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['one_variable_test_verified'] else 2)


if __name__ == '__main__':
    main()
