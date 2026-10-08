"""Named save switches and allocation inside the existing global-flag buffer.

New flags occupy the gap before the game's reserved item-flag range. No save
buffer is enlarged. Actual persistence must still be verified in the emulator.
"""

from dataclasses import dataclass
import re
import struct

from .kdm import KdmDocument
from .pickups import integer, record, text


@dataclass(frozen=True)
class SaveSwitch:
    name: str
    index: int


def global_flags(document: KdmDocument) -> tuple[SaveSwitch, ...]:
    if document.structures[21].fields != (3, 1):
        raise ValueError("Unsupported switch registry schema")
    result: list[SaveSwitch] = []
    for row in document.tables["gfSwitchTable"].values:
        fields = record(row, 2)
        name, index = text(fields[0]), integer(fields[1])
        if name:
            if not name.startswith("gf_") or index < 0:
                raise ValueError("Invalid global save flag")
            result.append(SaveSwitch(name, index))
        elif row is not document.tables["gfSwitchTable"].values[-1] or index:
            raise ValueError("Switch sentinel must be the final zero entry")
    if len({flag.name for flag in result}) != len(result):
        raise ValueError("Duplicate global save-flag name")
    return tuple(result)


def register_flags(source: bytes, names: tuple[str, ...]) -> tuple[bytes, tuple[SaveSwitch, ...]]:
    if len(set(names)) != len(names) or any(not re.fullmatch(r"gf_rando_[a-z0-9_]+", name) for name in names):
        raise ValueError("Randomizer flags require unique gf_rando_ names")
    original = KdmDocument(source)
    flags = global_flags(original)
    by_name = {flag.name: flag.index for flag in flags}
    if any(name in by_name for name in names):
        raise ValueError("Randomizer flag is already registered")
    reserved = by_name["gf_mobj_item_start"]
    used = {flag.index for flag in flags}
    start = max(index for index in used if index < reserved) + 1
    if start + len(names) > reserved:
        raise ValueError("Randomizer flags exceed the unused global-flag range")
    additions = tuple(SaveSwitch(name, start + offset) for offset, name in enumerate(names))
    if not additions:
        return source, ()
    document = KdmDocument(original.add_strings(names))
    table = document.tables["gfSwitchTable"]
    if table.type_id != 21 or not table.values or record(table.values[-1], 2)[0].value != "":
        raise ValueError("Expected a direct switch table ending with a sentinel")
    words = (len(table.values) + len(additions)) * 2
    if words > 0xFFFF:
        raise ValueError("Switch registry exceeds the KDM array size")
    pointers = {value: offset for offset, value in document.strings.items()}
    inserted = b"".join(struct.pack("<Ii", pointers[flag.name], flag.index) for flag in additions)
    insertion = table.values[-1].offset
    result = bytearray(document.data[:insertion] + inserted + document.data[insertion:])
    struct.pack_into("<H", result, table.address - 6, words)
    # This is a direct table in the last tables section: no pointed data arrays
    # are moved. Later table headers/records move together with their bytes.
    struct.pack_into("<I", result, 8 + 7 * 4, (document.sections[7] + len(inserted)) // 4)
    checked = global_flags(KdmDocument(bytes(result)))
    if checked != flags + additions:
        raise ValueError("Save-switch registry verification failed")
    return bytes(result), additions
