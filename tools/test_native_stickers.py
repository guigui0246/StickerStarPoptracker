"""Execute normal/direct and forced sticker guards against ROM-derived indices."""

import argparse
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.abilities import CODE_BASE, ability_patch
from randomizer.integrations.rom.sticker_guard import (
    ALBUM_ADD,
    COMMIT_ADD,
    FORCED_ADD,
    ITEM_LOOKUP,
    NORMAL_ADD,
    generic_save_indices,
    sticker_guard_patch,
)
from randomizer.integrations.rom.stickers import sticker_policy
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.pickups import record, text, integer
from randomizer.tests.test_abilities import fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-runtime", type=Path, required=True)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--item-data", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.arm_runtime.resolve()))
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE  # pyright: ignore[reportMissingImports]
    from unicorn.arm_const import (  # pyright: ignore[reportMissingImports]
        UC_ARM_REG_R0,
        UC_ARM_REG_R1,
        UC_ARM_REG_R2,
        UC_ARM_REG_R3,
        UC_ARM_REG_R4,
        UC_ARM_REG_R5,
        UC_ARM_REG_R6,
        UC_ARM_REG_R7,
        UC_ARM_REG_R8,
        UC_ARM_REG_R9,
        UC_ARM_REG_R10,
        UC_ARM_REG_R11,
        UC_ARM_REG_SP,
        UC_ARM_REG_LR,
        UC_ARM_REG_PC,
    )

    code = args.code.read_bytes()
    policy = sticker_policy(args.item_data.read_bytes())
    indices = generic_save_indices(args.item_data.read_bytes(), policy)
    native_rows = {
        text(fields[0]): fields
        for array in KdmDocument(args.item_data.read_bytes()).arrays.values()
        if array.type_id == 30
        for row in array.values
        for fields in [record(row, 19)]
    }
    names = list(policy.generic) + [sticker for sticker, _ in policy.things] + ["SL_PAGE", "REAL_FAN"]
    descriptors = {name: 0x08001000 + index * 80 for index, name in enumerate(names)}
    name_pointers = {name: 0x08008000 + index * 80 for index, name in enumerate(names)}
    stack = 0x0801F000
    fingerprint = bytes(range(16))
    count = 0
    for start in (1447, 1456, 1472):
        _, flags = fixture(start)
        flags.update({policy.flag(item): 1700 + index for index, item in enumerate(policy.generic)})
        patch = sticker_guard_patch(code, flags, fingerprint, policy, indices, ability_patch(code, flags, fingerprint))
        emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        emulator.mem_map(CODE_BASE, len(code))
        emulator.mem_write(CODE_BASE, code)
        for offset, data in patch.records:
            emulator.mem_write(CODE_BASE + offset, data)
        emulator.mem_map(0x08000000, 0x20000)
        for name in names:
            native_index = integer(native_rows[name][17])
            kind = integer(native_rows[name][18])
            data = bytearray(68)
            struct.pack_into("<I", data, 0, name_pointers[name])
            struct.pack_into("<II", data, 0x3C, native_index, kind)
            emulator.mem_write(descriptors[name], bytes(data))
            emulator.mem_write(name_pointers[name], name.encode() + b"\0")
        state = {"stop": 0, "writes": []}

        def on_code(uc, address, size, user_data):
            if address == state["stop"]:
                uc.emu_stop()
            elif address == ITEM_LOOKUP:
                pointer = uc.reg_read(UC_ARM_REG_R0)
                name = bytes(uc.mem_read(pointer, 80)).split(b"\0")[0].decode()
                if name not in descriptors:
                    raise AssertionError(f"Unexpected native item lookup: {name}")
                uc.reg_write(UC_ARM_REG_R0, descriptors[name])
                uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

        def on_write(uc, access, address, size, value, user_data):
            state["writes"].append((address, size))

        emulator.hook_add(UC_HOOK_CODE, on_code)
        emulator.hook_add(UC_HOOK_MEM_WRITE, on_write)
        preserved = (
            UC_ARM_REG_R4,
            UC_ARM_REG_R5,
            UC_ARM_REG_R6,
            UC_ARM_REG_R7,
            UC_ARM_REG_R8,
            UC_ARM_REG_R9,
            UC_ARM_REG_R10,
            UC_ARM_REG_R11,
        )
        for name in names:
            generic = name in policy.generic
            for valid in ("valid", "wrong_seed", "uninitialized", "null_owner"):
                for owned in (False, True):
                    for entry in (NORMAL_ADD, FORCED_ADD, COMMIT_ADD, ALBUM_ADD):
                        buffer = bytearray(384)

                        def set_bit(index):
                            buffer[index // 8] |= 1 << (index % 8)

                        if valid != "uninitialized":
                            set_bit(flags["gf_rando_seed_initialized"])
                        for bit in range(128):
                            if fingerprint[bit // 8] & 1 << (bit % 8):
                                set_bit(flags[f"gf_rando_seed_{bit:02d}"])
                        if valid == "wrong_seed":
                            bit = flags["gf_rando_seed_127"]
                            buffer[bit // 8] ^= 1 << (bit % 8)
                        if generic and owned:
                            set_bit(flags[policy.flag(name)])
                        emulator.mem_write(0x08000144, bytes(buffer))
                        emulator.mem_write(0x43C190, struct.pack("<I", 0 if valid == "null_owner" else 0x08000000))
                        registers = (
                            (0x08019000, 2, name_pointers[name], 0x0801A000)
                            if entry != FORCED_ADD
                            else (0x08019000, descriptors[name], 0x0801A000, 99)
                        )
                        for register, value in zip(
                            (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), registers, strict=True
                        ):
                            emulator.reg_write(register, value)
                        for index, register in enumerate(preserved):
                            emulator.reg_write(register, 0xCAFE0000 + index)
                        emulator.reg_write(UC_ARM_REG_SP, stack)
                        emulator.reg_write(UC_ARM_REG_LR, CODE_BASE)
                        state["stop"] = entry + 4
                        state["writes"] = []
                        emulator.emu_start(entry, 0, count=1000)
                        assert emulator.reg_read(UC_ARM_REG_PC) == entry + 4, "Guard failed to resume native insertion"
                        selected = policy.replacement if generic and not (valid == "valid" and owned) else name
                        if entry != FORCED_ADD:
                            assert emulator.reg_read(UC_ARM_REG_R2) == name_pointers[selected], (name, valid, owned)
                            assert emulator.reg_read(UC_ARM_REG_R1) == registers[1]
                            expected_sp = stack - 36
                        else:
                            assert emulator.reg_read(UC_ARM_REG_R1) == descriptors[selected], (name, valid, owned)
                            assert emulator.reg_read(UC_ARM_REG_R2) == registers[2]
                            expected_sp = stack - 24
                        assert emulator.reg_read(UC_ARM_REG_R0) == registers[0]
                        assert emulator.reg_read(UC_ARM_REG_R3) == registers[3]
                        assert emulator.reg_read(UC_ARM_REG_LR) == CODE_BASE
                        assert emulator.reg_read(UC_ARM_REG_SP) == expected_sp
                        assert all(
                            emulator.reg_read(register) == 0xCAFE0000 + index for index, register in enumerate(preserved)
                        )
                        assert bytes(emulator.mem_read(0x08000144, 384)) == bytes(buffer), "Guard wrote save flags"
                        assert all(stack - 256 <= address < address + size <= stack for address, size in state["writes"]), (
                            "Guard wrote outside its stack"
                        )
                        count += 1
        print(f"Native sticker guard executions passed: {count}", flush=True)


if __name__ == "__main__":
    main()
