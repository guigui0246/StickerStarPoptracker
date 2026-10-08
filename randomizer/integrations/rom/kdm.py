"""Lossless KDMR table inspection and same-size scalar edits.

Layout is validated against the supplied European dump. Original bytes,
padding, IDs, and array order are retained; unknown types fail explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import TypeAlias


@dataclass(frozen=True)
class KdmPointer:
    address: int
    type_id: int


Scalar: TypeAlias = int | float | str | bool | KdmPointer


@dataclass(frozen=True)
class KdmField:
    offset: int
    type_id: int
    value: Scalar | tuple[KdmField, ...]


@dataclass(frozen=True)
class KdmStructure:
    id: int
    fields: tuple[int, ...]
    size: int
    alignment: int


@dataclass(frozen=True)
class KdmArray:
    id: int
    address: int
    type_id: int
    field_count: int
    values: tuple[KdmField, ...]


class KdmDocument:
    """Immutable source bytes with validated typed views into each data array."""

    _formats = {0: "f", 1: "i", 2: "I", 3: "I", 4: "?", 7: "B", 8: "H"}
    _pointer_types = frozenset(range(10, 21))

    def __init__(self, data: bytes) -> None:
        if len(data) < 40 or data[:8] != b"KDMR\x00\x01\x01\x00":
            raise ValueError("Unsupported KDMR header")
        self.data = data
        self.sections = tuple(value * 4 for value in struct.unpack_from("<8I", data, 8))
        if self.sections[0] != 40 or list(self.sections) != sorted(self.sections):
            raise ValueError("Invalid KDM section offsets")
        self.structures: dict[int, KdmStructure] = {}
        self.strings: dict[int, str] = {}
        cursor = self.sections[0] + 4
        for _ in range(self.u32(self.sections[0])):
            end = data.find(b"\0", cursor, self.sections[1])
            if end < cursor:
                raise ValueError("Unterminated KDM string")
            self.strings[cursor] = data[cursor:end].decode("utf-8")
            cursor = self.align(end + 1, 4)
        if cursor != self.sections[1]:
            raise ValueError("KDM string count does not match section size")
        cursor = self.sections[4] + 4
        for _ in range(self.u32(self.sections[4])):
            identifier, count = self.unpack("HH", cursor)
            fields = tuple(self.u32(cursor + 12 + index * 4) for index in range(count))
            size = 0
            alignment = 1
            for field_type in fields:
                field_size, field_alignment = self.layout(field_type)
                size = self.align(size, field_alignment) + field_size
                alignment = max(alignment, field_alignment)
            if identifier in self.structures or identifier < 21:
                raise ValueError("Duplicate or reserved KDM structure ID")
            self.structures[identifier] = KdmStructure(
                identifier, fields, self.align(size, 4), max(alignment, 4)
            )
            cursor += 12 + count * 4
        if cursor != self.sections[5]:
            raise ValueError("KDM structure section size mismatch")
        self.arrays: dict[int, KdmArray] = {}
        cursor = self.sections[5] + 4
        for _ in range(self.u32(self.sections[5])):
            array, cursor = self.read_array(cursor)
            if array.address in self.arrays:
                raise ValueError("Duplicate KDM array address")
            self.arrays[array.address] = array
        if cursor != self.sections[6]:
            raise ValueError("KDM data section size mismatch")
        count = self.u32(self.sections[6])
        names = tuple(
            self.string(self.u32(self.sections[6] + 4 + index * 4))
            for index in range(count)
        )
        cursor = self.sections[6] + 4 + count * 4
        self.tables: dict[str, KdmArray] = {}
        for name in names:
            array, cursor = self.read_array(cursor)
            self.arrays[array.address] = array
            if name in self.tables:
                raise ValueError("Duplicate KDM table name")
            self.tables[name] = array
        if cursor != self.sections[7]:
            raise ValueError("KDM table section size mismatch")

    @staticmethod
    def align(value: int, alignment: int) -> int:
        return (value + alignment - 1) // alignment * alignment

    def unpack(self, fmt: str, offset: int) -> tuple[int, ...]:
        length = struct.calcsize("<" + fmt)
        if offset < 0 or offset + length > len(self.data):
            raise ValueError("KDM read outside file")
        return struct.unpack_from("<" + fmt, self.data, offset)

    def u32(self, offset: int) -> int:
        return self.unpack("I", offset)[0]

    def string(self, address: int) -> str:
        if address == 0:
            return ""
        if address not in self.strings:
            raise ValueError(f"Unknown KDM string pointer {address:#x}")
        return self.strings[address]

    def layout(self, type_id: int) -> tuple[int, int]:
        if type_id in self._formats:
            size = struct.calcsize("<" + self._formats[type_id])
            return size, size
        if type_id in self._pointer_types:
            return 4, 4
        if type_id in self.structures:
            definition = self.structures[type_id]
            return definition.size, definition.alignment
        raise ValueError(f"Unsupported KDM type {type_id}")

    def read_field(self, type_id: int, offset: int) -> KdmField:
        size, _ = self.layout(type_id)
        if offset + size > len(self.data):
            raise ValueError("KDM field outside file")
        if type_id in self.structures:
            children: list[KdmField] = []
            cursor = offset
            for child_type in self.structures[type_id].fields:
                child_size, alignment = self.layout(child_type)
                cursor = self.align(cursor, alignment)
                children.append(self.read_field(child_type, cursor))
                cursor += child_size
            return KdmField(offset, type_id, tuple(children))
        if type_id in self._pointer_types:
            return KdmField(offset, type_id, KdmPointer(self.u32(offset), type_id))
        value = struct.unpack_from("<" + self._formats[type_id], self.data, offset)[0]
        return KdmField(offset, type_id, self.string(value) if type_id == 3 else value)

    def read_array(self, offset: int) -> tuple[KdmArray, int]:
        identifier, words, type_id, field_count = self.unpack("4H", offset)
        address = offset + 8
        size, _ = self.layout(type_id)
        byte_count = words * 4
        if byte_count % size:
            raise ValueError("KDM array contains an incomplete record")
        end = address + byte_count
        if end > len(self.data):
            raise ValueError("KDM array exceeds file size")
        values = tuple(
            self.read_field(type_id, cursor) for cursor in range(address, end, size)
        )
        return KdmArray(identifier, address, type_id, field_count, values), end

    def pointed_array(self, pointer: KdmPointer) -> KdmArray:
        if pointer.address not in self.arrays:
            raise ValueError("Pointer does not reference a known data array")
        return self.arrays[pointer.address]

    def edit_strings(self, replacements: dict[int, str]) -> bytes:
        """Change only validated string-pointer fields using existing strings."""
        fields: dict[int, KdmField] = {}

        def gather(field: KdmField) -> None:
            if isinstance(field.value, tuple):
                for child in field.value:
                    gather(child)
            elif field.type_id == 3:
                fields[field.offset] = field

        for array in self.arrays.values():
            for field in array.values:
                gather(field)
        addresses = {value: address for address, value in self.strings.items()}
        addresses[""] = 0
        result = bytearray(self.data)
        for offset, value in replacements.items():
            if offset not in fields or value not in addresses:
                raise ValueError(
                    "String edit must target a known field and existing string"
                )
            struct.pack_into("<I", result, offset, addresses[value])
        return bytes(result)
