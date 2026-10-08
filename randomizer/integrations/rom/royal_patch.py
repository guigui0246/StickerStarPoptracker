"""Suppress original Royal ownership without rewriting source story flags."""

import re
import struct
from .ksm import KsmDocument
from .script_build import replace_body


FINAL_BOSS = "Script/Map/W6_BOS/w6_bos_04.bin"
INTERMISSIONS = tuple(f"Script/Map/InterMission/w{world}_itm_00.bin" for world in range(1, 6))


def disable_book_restoration(data: bytes) -> bytes:
    """Make the no-argument restoration function return, retaining every offset.

    The original debug script contains names the external compiler cannot
    parse. A bounded same-size bytecode edit avoids recompiling unrelated code.
    """
    document = KsmDocument(data)
    if document.version != 0x00010300:
        raise ValueError("Unsupported restoration bytecode version")
    name = b"royalseal_book_reset\0"
    matches = [match.start() for match in re.finditer(re.escape(name), data[document.sections[1]:document.sections[2]])]
    if len(matches) != 1:
        raise ValueError("Expected one Royal restoration function")
    name_offset = document.sections[1] + matches[0]
    header = name_offset - 36
    marker, identifier, public, temporaries, start, end, accumulator, label, size = struct.unpack_from("<9I", data, header)
    if marker != 0xFFFFFFFF or public or label or size * 4 < len(name):
        raise ValueError("Unsupported Royal restoration function metadata")
    base = document.sections[7] + 4
    words = document.word(document.sections[7])
    if not 0 <= start < start + 5 < end <= words:
        raise ValueError("Restoration function is outside the instruction section")
    if [document.word(base + offset * 4) for offset in (start, start + 1, start + 2, end - 1)] != [5, identifier, 8, 9]:
        raise ValueError("Restoration function has an unexpected call frame")
    result = bytearray(data)
    body = start + 3
    for offset in range(body, end - 1):
        struct.pack_into("<I", result, base + offset * 4, 2)  # no-op
    struct.pack_into("<2I", result, base + body * 4, 3, 0x40)  # return; empty expression
    KsmDocument(bytes(result))
    return bytes(result)


def suppress_royal_grant(filename: str, source: str) -> str:
    if filename in INTERMISSIONS:
        result, count = re.subn(r"\bpouch_set_royal_seal\*?\(localVar0\);", "", source)
        if count != 1:
            raise ValueError("Expected one original intermission Royal grant")
        return result
    if filename == FINAL_BOSS:
        result, count = re.subn(r"\bpouch_set_royal_seal\*?\(pouch_royal_w6\);", "", source)
        if count != 1:
            raise ValueError("Expected one original final Royal grant")
        return result
    if filename == "Script/ksm_evtcond.bin":
        # This debug restoration function clears the pouch and reconstructs
        # ownership from source completion flags. Neither operation is valid
        # for shuffled rewards; preserve the current pouch instead.
        return replace_body(source, "royalseal_book_reset", "\treturn*;")
    raise ValueError("Unsupported original Royal reward script")
