"""Execute the generated ARM guard with an isolated Unicorn installation."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.abilities import ATTACH_FUNCTION, CODE_BASE, ability_patch
from randomizer.tests.test_abilities import fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-runtime", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.arm_runtime.resolve()))
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_MEM_WRITE
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR
    count = 0
    for start in (1447, 1456, 1472):
        code, flags = fixture(start)
        fingerprint = bytes(range(16))
        patch = ability_patch(code, flags, fingerprint)
        for valid in ("valid", "uninitialized", "wrong_seed", "null_owner"):
            for owned in range(4):
                for request in range(8):
                    emulator = Uc(UC_ARCH_ARM, UC_MODE_ARM)
                    emulator.mem_map(CODE_BASE, len(code))
                    emulator.mem_write(CODE_BASE, code)
                    for offset, data in patch.records:
                        emulator.mem_write(CODE_BASE + offset, data)
                    emulator.mem_map(0x8000000, 0x3000)
                    gf_owner, pouch = 0x8000000, 0x8001000
                    emulator.mem_write(0x43C190, (0 if valid == "null_owner" else gf_owner).to_bytes(4, "little"))
                    buffer = bytearray(384)

                    def set_bit(index: int) -> None:
                        buffer[index // 8] |= 1 << (index % 8)

                    if valid != "uninitialized":
                        set_bit(flags["gf_rando_seed_initialized"])
                    for bit in range(128):
                        if fingerprint[bit // 8] & (1 << (bit % 8)):
                            set_bit(flags[f"gf_rando_seed_{bit:02d}"])
                    if valid == "wrong_seed":
                        index = flags["gf_rando_seed_127"]
                        buffer[index // 8] ^= 1 << (index % 8)
                    for bit, ability in enumerate(("hammer", "paperization")):
                        if owned & (1 << bit):
                            set_bit(flags[f"gf_rando_ability_{ability}"])
                    emulator.mem_write(gf_owner + 0x144, bytes(buffer))
                    emulator.mem_write(pouch + 0x13C, (0x80).to_bytes(4, "little"))
                    emulator.reg_write(UC_ARM_REG_R0, pouch)
                    emulator.reg_write(UC_ARM_REG_R1, request)
                    preserved = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR)
                    for index, register in enumerate(preserved):
                        emulator.reg_write(register, 0xABCD0000 + index)
                    stop = 0x100100
                    emulator.reg_write(UC_ARM_REG_LR, stop)
                    writes = []
                    emulator.hook_add(UC_HOOK_MEM_WRITE, lambda _uc, _access, address, size, value, _user: writes.append((address, size, value)))
                    emulator.emu_start(ATTACH_FUNCTION, stop, count=200)
                    permitted = (1 if owned & 1 else 0) | (4 if owned & 2 else 0) if valid == "valid" else 0
                    expected = 0x80 | request & (0xFFFFFFFA | permitted)
                    assert int.from_bytes(emulator.mem_read(pouch + 0x13C, 4), "little") == expected, (start, valid, owned, request)
                    assert writes == [(pouch + 0x13C, 4, expected)], writes
                    assert bytes(emulator.mem_read(gf_owner + 0x144, 384)) == bytes(buffer)
                    assert emulator.reg_read(UC_ARM_REG_R0) == pouch
                    for index, register in enumerate(preserved):
                        assert emulator.reg_read(register) == (stop if register == UC_ARM_REG_LR else 0xABCD0000 + index)
                    count += 1
    print(f"Passed {count} native ARM ability executions: ownership, seed guards, ABI and write bounds.")


if __name__ == "__main__":
    main()
