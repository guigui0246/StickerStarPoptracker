"""Execute native variable-arena initialization and allocator boundary cases."""

import argparse
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.runtime_pool import CELL_SIZE, EXPANDED_LIMIT, ORIGINAL_LIMIT, expand_variable_pool


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-runtime", type=Path, required=True)
    parser.add_argument("--code", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.arm_runtime.resolve()))
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE  # pyright: ignore[reportMissingImports]
    from unicorn.arm_const import (  # pyright: ignore[reportMissingImports]
        UC_ARM_REG_R0,
        UC_ARM_REG_R1,
        UC_ARM_REG_SP,
        UC_ARM_REG_LR,
        UC_ARM_REG_PC,
    )

    code = args.code.read_bytes()
    patch = expand_variable_pool(code)
    pool_global = struct.unpack_from("<I", code, 0x1B4208)[0]
    arena, stack, stop = 0x08000000, 0x0811F000, 0x100100

    def machine(expanded: bool):
        uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(0x100000, len(code))
        uc.mem_write(0x100000, code)
        if expanded:
            for offset, raw in patch.records:
                uc.mem_write(0x100000 + offset, raw)
        uc.mem_map(arena, EXPANDED_LIMIT * CELL_SIZE)
        uc.mem_map(0x08100000, 0x20000)
        uc.reg_write(UC_ARM_REG_SP, stack)
        uc.reg_write(UC_ARM_REG_LR, stop)
        return uc

    allocations = []
    uc = machine(True)

    def initialize_hook(uc, address, size, data):
        if address == 0x10A3BC:
            uc.emu_stop()
        elif address == 0x2B780C:
            allocations.append(uc.reg_read(UC_ARM_REG_R0))
            uc.reg_write(UC_ARM_REG_R0, arena)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif address == 0x2B8520:
            assert uc.reg_read(UC_ARM_REG_R1) == EXPANDED_LIMIT * CELL_SIZE
            uc.mem_write(arena, bytes(EXPANDED_LIMIT * CELL_SIZE))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
        elif address == 0x2B36A0:
            pointer = uc.reg_read(UC_ARM_REG_R0)
            assert arena <= pointer < arena + EXPANDED_LIMIT * CELL_SIZE
            uc.mem_write(pointer, bytes(CELL_SIZE))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    uc.hook_add(UC_HOOK_CODE, initialize_hook)
    uc.emu_start(0x10A36C, 0, count=1000000)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x10A3BC
    assert allocations == [EXPANDED_LIMIT * CELL_SIZE]
    raw = bytes(uc.mem_read(arena, EXPANDED_LIMIT * CELL_SIZE))
    assert all(struct.unpack_from("<I", raw, index * CELL_SIZE + 8)[0] == 13 for index in range(EXPANDED_LIMIT))

    cases = (
        (False, ORIGINAL_LIMIT, ORIGINAL_LIMIT, None),
        (True, ORIGINAL_LIMIT, ORIGINAL_LIMIT, ORIGINAL_LIMIT),
        (True, EXPANDED_LIMIT - 1, EXPANDED_LIMIT - 1, EXPANDED_LIMIT - 1),
        (True, EXPANDED_LIMIT, 0, 0),
        (True, 0, None, None),
    )
    for expanded, cursor, free, expected in cases:
        uc = machine(expanded)
        limit = EXPANDED_LIMIT if expanded else ORIGINAL_LIMIT
        raw = bytearray(EXPANDED_LIMIT * CELL_SIZE)
        if free is not None:
            struct.pack_into("<I", raw, free * CELL_SIZE + 8, 13)
        uc.mem_write(arena, bytes(raw))
        uc.mem_write(pool_global + 0x10, struct.pack("<II", arena, cursor))
        uc.reg_write(UC_ARM_REG_R0, 0)

        def allocator_hook(uc, address, size, data):
            if address == stop:
                uc.emu_stop()
            elif address in (0x2B36A0, 0x29F514, 0x2ACE0C):
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        def write_hook(uc, access, address, size, value, data):
            if arena <= address < arena + EXPANDED_LIMIT * CELL_SIZE:
                assert address + size <= arena + limit * CELL_SIZE

        uc.hook_add(UC_HOOK_CODE, allocator_hook)
        uc.hook_add(UC_HOOK_MEM_WRITE, write_hook)
        uc.emu_start(0x2B4134, 0, count=1000000)
        assert uc.reg_read(UC_ARM_REG_PC) == stop
        actual = uc.reg_read(UC_ARM_REG_R0)
        assert actual == (0 if expected is None else arena + expected * CELL_SIZE), (expanded, cursor, free, hex(actual))
    print("Native ARM arena initialization and five allocator boundary cases passed")


if __name__ == "__main__":
    main()
