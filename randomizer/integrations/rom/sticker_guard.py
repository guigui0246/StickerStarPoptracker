"""Bounded ARM conversion at normal insertion and forced-item dispatch.

Runtime item records retain their KDM save index at +0x3c and kind at +0x40.
The forced dispatch must replace the descriptor, since its subsequent relocation
uses that descriptor again. Normal insertion instead receives an item-name pointer.
"""

import hashlib
import struct

from .abilities import CODE_BASE, TEXT_END, TEXT_LIMIT, CodePatch, branch, immediate
from .kdm import KdmDocument
from .pickups import integer, record, text
from .stickers import StickerPolicy

NORMAL_ADD = 0x278E90  # Placement feasibility only, not an inventory write.
FORCED_ADD = 0x352DDC
COMMIT_ADD = 0x270EAC  # Commit plus acquisition presentation.
ALBUM_ADD = 0x2D8208  # Lowest named-sticker album insertion.
ITEM_LOOKUP = 0x285C1C
NORMAL_PREFIX = bytes.fromhex("f04f2de90060a0e11cd04de20140a0e1")
FORCED_PREFIX = bytes.fromhex("f0412de90060a0e10140a0e1000091e5")
LOOKUP_PREFIX = bytes.fromhex("f0412de90020a0e30080a0e174409fe5")
COMMIT_PREFIX = bytes.fromhex("f04f2de90050a0e10270a0e101a0a0e1")
ALBUM_PREFIX = bytes.fromhex("f04f2de91cd04de20140a0e10090a0e1")
INSERTION_HOOKS = frozenset({NORMAL_ADD, FORCED_ADD, COMMIT_ADD, ALBUM_ADD})


def generic_save_indices(data: bytes, policy: StickerPolicy) -> dict[str, int]:
    document = KdmDocument(data)
    if document.structures[30].size != 68:
        raise ValueError("Unsupported native item descriptor layout")
    rows = {
        text(fields[0]): fields
        for array in document.arrays.values()
        if array.type_id == 30
        for row in array.values
        for fields in [record(row, 19)]
    }
    result = {}
    for item in policy.generic:
        fields = rows[item]
        if (
            integer(fields[18]) != 4
            or fields[17].offset - fields[0].offset != 0x3C
            or fields[18].offset - fields[0].offset != 0x40
        ):
            raise ValueError("Generic item does not match the verified runtime schema")
        result[item] = integer(fields[17])
    return result


def sticker_guard_patch(
    code: bytes,
    flags: dict[str, int],
    fingerprint: bytes,
    policy: StickerPolicy,
    indices: dict[str, int],
    ability: CodePatch | None = None,
) -> CodePatch:
    if len(code) != 0x34E000 or len(fingerprint) != 16 or any(code[TEXT_END - CODE_BASE : TEXT_LIMIT - CODE_BASE]):
        raise ValueError("Unsupported executable or occupied ARM padding")
    for address, original in (
        (NORMAL_ADD, NORMAL_PREFIX),
        (FORCED_ADD, FORCED_PREFIX),
        (COMMIT_ADD, COMMIT_PREFIX),
        (ALBUM_ADD, ALBUM_PREFIX),
        (ITEM_LOOKUP, LOOKUP_PREFIX),
    ):
        if code[address - CODE_BASE : address - CODE_BASE + len(original)] != original:
            raise ValueError("Unsupported native sticker insertion revision")
    if (
        set(indices) != set(policy.generic)
        or len(set(indices.values())) != len(indices)
        or any(type(index) is not int or not 0 <= index <= 200 for index in indices.values())
    ):
        raise ValueError("Generic save indices must be distinct and within the verified range")
    ownership = [flags[policy.flag(item)] for item in policy.generic]
    if (
        len(ownership) >= 255
        or ownership != list(range(ownership[0], ownership[0] + len(ownership)))
        or not 1446 <= ownership[0] <= ownership[-1] < 2560
    ):
        raise ValueError("Native generic ownership flags must be contiguous and save-safe")
    seed = [flags[f"gf_rando_seed_{bit:02d}"] for bit in range(128)]
    if seed != list(range(seed[0], seed[0] + 128)) or any(
        not 0 <= index < 2560 for index in [*seed, flags["gf_rando_seed_initialized"]]
    ):
        raise ValueError("Invalid seed flag layout")
    previous = ability.records if ability else ()
    start = TEXT_END + (len(ability.records[1][1]) if ability else 0)
    if ability and (
        ability.source_sha256 != hashlib.sha256(code).hexdigest() or ability.records[1][0] != TEXT_END - CODE_BASE
    ):
        raise ValueError("Ability and sticker guards must share the same original executable")
    words: list[int] = []
    descriptions: list[str] = []
    labels: dict[str, int] = {}
    fixups: list[tuple[int, str, bool, int]] = []
    literals: list[tuple[int, int, int | str]] = []

    def emit(word: int, description: str) -> None:
        words.append(word)
        descriptions.append(description)

    def label(name: str) -> None:
        labels[name] = len(words)

    def jump(name: str, *, link: bool = False, condition: int = 14) -> None:
        fixups.append((len(words), name, link, condition))
        condition_name = {0: "eq", 1: "ne", 8: "hi", 14: ""}[condition]
        emit(0, f"b{'l' if link else ''}{condition_name} rando_sticker_{name}")

    def call(address: int) -> None:
        emit(branch(start + len(words) * 4, address) | 0x01000000, f"bl 0x{address:08x}")

    def literal(register: int, value: int | str) -> None:
        literals.append((len(words), register, value))
        emit(0, f"ldr r{register}, [pc, literal]")

    entries = (
        ("normal", NORMAL_ADD, NORMAL_PREFIX, True),
        ("forced", FORCED_ADD, FORCED_PREFIX, False),
        ("commit", COMMIT_ADD, COMMIT_PREFIX, True),
        ("album", ALBUM_ADD, ALBUM_PREFIX, True),
    )
    for name, entry, original, string_input in entries:
        label(name)
        emit(0xE92D401F, "push {r0-r4, lr}")
        emit(0xE1A00002 if string_input else 0xE1A00001, "mov r0, r2" if string_input else "mov r0, r1")
        if string_input:
            call(ITEM_LOOKUP)
        jump("filter", link=True)
        if string_input:
            emit(0xE5900000, "ldr r0, [r0] ; selected item name")
        emit(0xE58D0008 if string_input else 0xE58D0004, "str r0, [sp, #8]" if string_input else "str r0, [sp, #4]")
        emit(0xE8BD401F, "pop {r0-r4, lr}")
        emit(struct.unpack_from("<I", original)[0], "original native register-save prologue")
        emit(branch(start + len(words) * 4, entry + 4), f"b 0x{entry + 4:08x}")
    label("filter")
    emit(0xE92D4070, "push {r4-r6, lr}")
    emit(0xE1A04000, "mov r4, r0 ; original descriptor")
    emit(0xE5901040, "ldr r1, [r0, #0x40] ; native kind")
    emit(0xE3510004, "cmp r1, #4")
    jump("original", condition=1)
    emit(0xE590103C, "ldr r1, [r0, #0x3c] ; native save index")
    emit(0xE35100C8, "cmp r1, #200")
    jump("original", condition=8)
    literal(3, "table")
    emit(0xE7D35001, "ldrb r5, [r3, r1] ; generic ownership rank")
    emit(0xE35500FF, "cmp r5, #255 ; not a generic sticker")
    jump("original", condition=0)
    literal(2, 0x43C190)
    emit(0xE5922000, "ldr r2, [r2] ; GF owner")
    emit(0xE3520000, "cmp r2, #0")
    jump("convert", condition=0)

    def load_flag(index: int) -> None:
        emit(0xE5923000 | (0x144 + index // 32 * 4), f"ldr r3, [r2, #0x{0x144 + index // 32 * 4:x}]")

    initialized = flags["gf_rando_seed_initialized"]
    load_flag(initialized)
    emit(0xE3130000 | immediate(1 << (initialized % 32)), "tst r3, #seed_initialized_mask")
    jump("convert", condition=0)
    masks: dict[int, tuple[int, int]] = {}
    for bit, index in enumerate(seed):
        mask, value = masks.get(index // 32, (0, 0))
        mask |= 1 << (index % 32)
        if fingerprint[bit // 8] & 1 << (bit % 8):
            value |= 1 << (index % 32)
        masks[index // 32] = mask, value
    for word, (mask, value) in sorted(masks.items()):
        load_flag(word * 32)
        if mask != 0xFFFFFFFF:
            literal(12, mask)
            emit(0xE003300C, "and r3, r3, r12")
        literal(12, value)
        emit(0xE153000C, "cmp r3, r12 ; seed word")
        jump("convert", condition=1)
    literal(3, ownership[0])
    emit(0xE0855003, "add r5, r5, r3 ; ownership GF index")
    emit(0xE1A032A5, "mov r3, r5, lsr #5")
    emit(0xE0823103, "add r3, r2, r3, lsl #2")
    emit(0xE5933144, "ldr r3, [r3, #0x144]")
    emit(0xE205501F, "and r5, r5, #31")
    emit(0xE3A0C001, "mov r12, #1")
    emit(0xE113051C, "tst r3, r12, lsl r5")
    jump("original", condition=1)
    label("convert")
    literal(0, "replacement")
    call(ITEM_LOOKUP)
    emit(0xE8BD8070, "pop {r4-r6, pc}")
    label("original")
    emit(0xE1A00004, "mov r0, r4")
    emit(0xE8BD8070, "pop {r4-r6, pc}")
    for position, name, link, condition in fixups:
        words[position] = branch(start + position * 4, start + labels[name] * 4, condition) | (0x01000000 if link else 0)
    for position, register, literal_value in literals:
        displacement = (len(words) - position) * 4 - 8
        if not 0 <= displacement <= 4095:
            raise ValueError("Sticker guard literal exceeds ARM range")
        words[position] = 0xE59F0000 | register << 12 | displacement
        if isinstance(literal_value, str):
            literals_value = len(words)
            emit(0, f"literal address: {literal_value}")
            fixups.append((literals_value, literal_value, False, -1))
        else:
            emit(literal_value, "literal data")
    label("table")
    table = bytearray(b"\xff" * 204)
    for rank, item in enumerate(policy.generic):
        table[indices[item]] = rank
    for word in struct.unpack("<51I", table):
        emit(word, "generic save-index lookup data")
    label("replacement")
    name_data = policy.replacement.encode("ascii") + b"\0"
    name_data += bytes((-len(name_data)) % 4)
    for word in struct.unpack(f"<{len(name_data) // 4}I", name_data):
        emit(word, "replacement name data")
    for position, name, _, condition in fixups:
        if condition == -1:
            words[position] = start + labels[name] * 4
    cave = struct.pack(f"<{len(words)}I", *words)
    if start + len(cave) > TEXT_LIMIT:
        raise ValueError("Combined native guards exceed existing executable padding")
    hooks = tuple(
        (entry - CODE_BASE, struct.pack("<I", branch(entry, start + labels[name] * 4))) for name, entry, _, _ in entries
    )
    records = previous + hooks + ((start - CODE_BASE, cave),)
    result = bytearray(code)
    for offset, data in records:
        result[offset : offset + len(data)] = data
    assembly = [ability.assembly if ability else ".syntax unified\n.arm\n"]
    for (name, _, _, _), (offset, data) in zip(entries, hooks, strict=True):
        assembly.extend(
            [
                f'.section .rando_sticker_hook_{name},"ax",%progbits',
                f"/* Place at 0x{CODE_BASE + offset:08x}. */",
                f"    .word 0x{struct.unpack('<I', data)[0]:08x} /* b rando_sticker_{name} */",
            ]
        )
    assembly.extend(['.section .rando_sticker_guard,"ax",%progbits', f"/* Place at 0x{start:08x}. */"])
    names = {position: name for name, position in labels.items()}
    for position, (word, description) in enumerate(zip(words, descriptions, strict=True)):
        if position in names:
            assembly.append(f"rando_sticker_{names[position]}:")
        assembly.append(f"    .word 0x{word:08x} /* 0x{start + position * 4:08x}: {description} */")
    return CodePatch(records, hashlib.sha256(code).hexdigest(), hashlib.sha256(result).hexdigest(), "\n".join(assembly) + "\n")
