"""Bounded ARM guard for native Hammer/Paperization accessory attachments.

The native player controller tests Hammer bit 1 and Kersti bit 4. Original
attachment calls retain every other bit. Shuffled abilities require their own
save flags and matching seed fingerprint before those bits may be added.
"""

from dataclasses import dataclass
import hashlib
import struct

CODE_BASE = 0x100000
ATTACH_FUNCTION = 0x2D81C0
TEXT_END = 0x3D6BB8
TEXT_LIMIT = 0x3D7000
ORIGINAL_ATTACH = bytes.fromhex("3c2190e5021081e13c1180e51eff2fe1")


def immediate(value: int) -> int:
    for rotate in range(16):
        bits = rotate * 2
        candidate = ((value << bits) | (value >> (32 - bits if bits else 32))) & 0xFFFFFFFF
        if candidate < 256:
            return rotate << 8 | candidate
    raise ValueError("Value cannot be encoded as an ARM immediate")


def branch(source: int, target: int, condition: int = 14) -> int:
    displacement = target - source - 8
    if displacement % 4 or not -(1 << 25) <= displacement < (1 << 25):
        raise ValueError("Native branch is unaligned or outside ARM range")
    return condition << 28 | 0x0A000000 | (displacement // 4 & 0xFFFFFF)


@dataclass(frozen=True)
class CodePatch:
    records: tuple[tuple[int, bytes], ...]
    source_sha256: str
    patched_sha256: str

    def ips(self) -> bytes:
        result = bytearray(b"PATCH")
        for offset, data in self.records:
            if not 0 <= offset < 0x1000000 or not 0 < len(data) < 65536 or offset == 0x454F46:
                raise ValueError("Native patch record exceeds IPS limits")
            result.extend(offset.to_bytes(3, "big") + len(data).to_bytes(2, "big") + data)
        return bytes(result) + b"EOF"

    @property
    def signatures(self) -> list[dict[str, str | int]]:
        return [{"address": CODE_BASE + offset, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()} for offset, data in self.records]


def ability_patch(code: bytes, flags: dict[str, int], fingerprint: bytes) -> CodePatch:
    if len(code) != 0x34E000 or code[ATTACH_FUNCTION - CODE_BASE:ATTACH_FUNCTION - CODE_BASE + 16] != ORIGINAL_ATTACH:
        raise ValueError("Unsupported native accessory function revision")
    if len(fingerprint) != 16 or any(code[TEXT_END - CODE_BASE:TEXT_LIMIT - CODE_BASE]):
        raise ValueError("Executable padding is occupied or seed identity is invalid")
    expected_flags = [flags[f"gf_rando_seed_{index:02d}"] for index in range(128)]
    if expected_flags != list(range(expected_flags[0], expected_flags[0] + 128)):
        raise ValueError("Native fingerprint flags must be contiguous")
    required = [flags["gf_rando_seed_initialized"], *expected_flags,
                flags["gf_rando_ability_hammer"], flags["gf_rando_ability_paperization"]]
    if any(type(index) is not int or not 0 <= index < 2560 for index in required):
        raise ValueError("Ability flags must remain outside native reserved item flags")
    words: list[int] = []
    labels: dict[str, int] = {}
    branches: list[tuple[int, str, int]] = []
    literals: list[tuple[int, int, int]] = []

    def jump(label: str, condition: int = 14) -> None:
        branches.append((len(words), label, condition))
        words.append(0)

    def literal(register: int, value: int) -> None:
        literals.append((len(words), register, value))
        words.append(0)

    def flag_word(index: int) -> None:
        words.append(0xE5923000 | (0x144 + index // 32 * 4))  # ldr r3,[r2,#GF word]

    def test(index: int) -> None:
        words.append(0xE3130000 | immediate(1 << (index % 32)))

    literal(2, 0x43C190)
    words.extend((0xE5922000, 0xE3520000))  # owner pointer, cmp owner,#0
    jump("deny", 0)
    flag_word(flags["gf_rando_seed_initialized"])
    test(flags["gf_rando_seed_initialized"])
    jump("deny", 0)
    masks: dict[int, tuple[int, int]] = {}
    for bit, index in enumerate(expected_flags):
        mask, value = masks.get(index // 32, (0, 0))
        mask |= 1 << (index % 32)
        if fingerprint[bit // 8] & (1 << (bit % 8)):
            value |= 1 << (index % 32)
        masks[index // 32] = mask, value
    for word, (mask, value) in sorted(masks.items()):
        flag_word(word * 32)
        if mask != 0xFFFFFFFF:
            try:
                encoded = immediate(mask)
            except ValueError:
                literal(12, mask)
                words.append(0xE003300C)  # and r3,r3,ip
            else:
                words.append(0xE2033000 | encoded)  # and r3,r3,#mask
        literal(12, value)
        words.append(0xE153000C)  # cmp r3,ip
        jump("deny", 1)
    for ability, native_bit in (("hammer", 1), ("paperization", 4)):
        index = flags[f"gf_rando_ability_{ability}"]
        flag_word(index)
        test(index)
        words.append(0x03C11000 | immediate(native_bit))  # biceq r1,r1,#ability
    jump("grant")
    labels["deny"] = len(words)
    words.append(0xE3C11005)  # bic r1,r1,#Hammer|Kersti
    labels["grant"] = len(words)
    words.extend(struct.unpack("<4I", ORIGINAL_ATTACH))
    for position, label, condition in branches:
        words[position] = branch(TEXT_END + position * 4, TEXT_END + labels[label] * 4, condition)
    for position, register, value in literals:
        displacement = (len(words) - position) * 4 - 8
        if not 0 <= displacement <= 4095:
            raise ValueError("Native literal exceeds ARM range")
        words[position] = 0xE59F0000 | register << 12 | displacement
        words.append(value)
    cave = struct.pack(f"<{len(words)}I", *words)
    if TEXT_END + len(cave) > TEXT_LIMIT:
        raise ValueError("Ability guard exceeds existing executable padding")
    records = ((ATTACH_FUNCTION - CODE_BASE, struct.pack("<I", branch(ATTACH_FUNCTION, TEXT_END))),
               (TEXT_END - CODE_BASE, cave))
    result = bytearray(code)
    for offset, data in records:
        result[offset:offset + len(data)] = data
    return CodePatch(records, hashlib.sha256(code).hexdigest(), hashlib.sha256(result).hexdigest())
