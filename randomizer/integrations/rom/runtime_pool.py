"""Signature-checked ARM expansion of the native script-variable arena.

The arena contains 24-byte cells. Allocation, clearing, initialization and both
allocator scans must use matching bounds; changing only a scan would overrun
the original buffer. This adds 288 KiB of runtime heap and changes no save data.
"""

import hashlib
import struct

from .abilities import CODE_BASE, CodePatch, immediate

ORIGINAL_LIMIT = 0x3000
EXPANDED_LIMIT = 0x6000
CELL_SIZE = 24
POOL_SITES = (
    (0x10A36C, 0xE3A00912, EXPANDED_LIMIT * CELL_SIZE, "mov r0, #0x90000 // allocate bytes"),
    (0x10A37C, 0xE3A01912, EXPANDED_LIMIT * CELL_SIZE, "mov r1, #0x90000 // clear bytes"),
    (0x10A3A8, 0xE3540A03, EXPANDED_LIMIT, "cmp r4, #0x6000 // initialize cells"),
    (0x2B4150, 0xE3550A03, EXPANDED_LIMIT, "cmp r5, #0x6000 // forward allocation scan"),
    (0x2B41B0, 0xE3550A03, EXPANDED_LIMIT, "cmp r5, #0x6000 // wrapped allocation scan"),
)


def expand_variable_pool(code: bytes, previous: CodePatch | None = None) -> CodePatch:
    if len(code) != 0x34E000:
        raise ValueError("Unsupported executable size for variable-pool expansion")
    digest = hashlib.sha256(code).hexdigest()
    if previous is not None and previous.source_sha256 != digest:
        raise ValueError("Variable-pool and executable guards require the same source")
    records = list(previous.records) if previous else []
    assembly = previous.assembly if previous else ".syntax unified\n.arm\n"
    for address, original, value, mnemonic in POOL_SITES:
        offset = address - CODE_BASE
        if code[offset : offset + 4] != struct.pack("<I", original):
            raise ValueError(f"Unsupported variable-pool instruction at 0x{address:08x}")
        if any(offset < start + len(data) and start < offset + 4 for start, data in records):
            raise ValueError("Variable-pool patch overlaps another executable patch")
        word = (original & ~0xFFF) | immediate(value)
        records.append((offset, struct.pack("<I", word)))
        assembly += (
            f'\n.section .text.rando_pool_{address:x}, "ax"\n.org 0x{address:08x}\n    .word 0x{word:08x} // {mnemonic}\n'
        )
    patched = bytearray(code)
    for offset, data in records:
        patched[offset : offset + len(data)] = data
    return CodePatch(tuple(records), digest, hashlib.sha256(patched).hexdigest(), assembly)
