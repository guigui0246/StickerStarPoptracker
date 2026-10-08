"""Lossless typed KSMR metadata for locating script rewards and flag references.

This reader preserves exact float bits and original identifier/import ordering.
It does not treat unknown bytecode as understood or rewrite function bodies.
"""

from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import cast


class KsmValueType(IntEnum):
    FLOAT = 0
    INTEGER = 1
    UNSIGNED = 2
    STRING = 3
    ALLOCATION = 4
    REFERENCE = 5
    POINTER = 6
    BOOLEAN = 7
    FUNCTION = 8
    FUNCTION_ALT = 9
    EMPTY_STRING = 10
    SELF = 11
    TABLE = 12
    DELETED = 13
    UNINITIALIZED = 14
    SAVE_VARIABLE = 20


@dataclass(frozen=True)
class KsmVariable:
    id: int
    name: str | None
    type: KsmValueType
    flags: int
    value: int | float | str | bool
    value_offset: int
    string_capacity: int = 0


@dataclass(frozen=True)
class KsmImport:
    id: int
    name: str
    type_id: int
    uses: int
    file_id: int | None


class KsmDocument:
    def __init__(self, data: bytes) -> None:
        if len(data) < 44 or len(data) % 4 or data[:4] != b"KSMR":
            raise ValueError("Invalid KSMR header")
        self.data = data
        self.version = self.word(4)
        if self.version not in {0x00010300, 0x00010302}:
            raise ValueError("Unsupported KSM version")
        self.sections = tuple(value * 4 for value in struct.unpack_from("<8I", data, 8))
        if (
            list(self.sections) != sorted(self.sections)
            or self.sections[0] < 44
            or self.sections[-1] + 4 > len(data)
        ):
            raise ValueError("Invalid KSM section offsets")
        self.statics = self.variables(2)
        self.constants = self.variables(4)
        self.globals = self.variables(6)
        self.imports = self.read_imports()

    def word(self, offset: int) -> int:
        if offset < 0 or offset + 4 > len(self.data):
            raise ValueError("KSM word outside file")
        return int.from_bytes(self.data[offset : offset + 4], "little")

    def string(self, offset: int, limit: int) -> tuple[str, int, int]:
        capacity = self.word(offset) * 4
        start = offset + 4
        end = start + capacity
        if end > limit:
            raise ValueError("KSM string exceeds its section")
        text = self.data[start:end].split(b"\0")[0].decode("utf-8")
        return text, end, capacity

    def variables(self, section: int) -> tuple[KsmVariable, ...]:
        cursor = self.sections[section] + 4
        end = self.sections[section + 1]
        result: list[KsmVariable] = []
        for _ in range(self.word(self.sections[section])):
            if cursor + 16 > end:
                raise ValueError("Truncated KSM variable")
            marker, identifier, flags, raw = struct.unpack_from(
                "<4I", self.data, cursor
            )
            if marker not in {0, 0xFFFFFFFF}:
                raise ValueError("Invalid KSM variable name marker")
            kind = KsmValueType(flags & 0xFF)
            value_offset = cursor + 12
            cursor += 16
            name = None
            if marker:
                name, cursor, _ = self.string(cursor, end)
            capacity = 0
            value: int | float | str | bool = raw
            if kind == KsmValueType.STRING:
                if raw:
                    raise ValueError("Invalid string variable payload")
                value_offset = cursor + 4
                value, cursor, capacity = self.string(cursor, end)
            elif kind == KsmValueType.FLOAT:
                value = cast(
                    float, struct.unpack_from("<f", self.data, value_offset)[0]
                )
            elif kind == KsmValueType.INTEGER:
                value = raw if raw < 0x80000000 else raw - 0x100000000
            elif kind == KsmValueType.BOOLEAN:
                if raw not in {0, 1}:
                    raise ValueError("Invalid KSM boolean")
                value = bool(raw)
            result.append(
                KsmVariable(
                    identifier, name, kind, flags, value, value_offset, capacity
                )
            )
        if cursor != end:
            raise ValueError("KSM variable count does not match section size")
        if len({variable.id for variable in result}) != len(result):
            raise ValueError("Duplicate KSM variable IDs")
        return tuple(result)

    def read_imports(self) -> tuple[KsmImport, ...]:
        cursor = self.sections[5] + 4
        end = self.sections[6]
        result: list[KsmImport] = []
        for _ in range(self.word(self.sections[5])):
            header_size = 28 if self.version == 0x00010300 else 20
            if cursor + header_size > end or self.word(cursor) != 0xFFFFFFFF:
                raise ValueError("Invalid KSM import")
            usage = self.word(cursor + 4)
            kind = self.word(cursor + 8)
            identifier = self.word(cursor + (16 if header_size == 28 else 12))
            if any(
                self.word(position)
                for position in range(
                    cursor + header_size - (8 if header_size == 28 else 4),
                    cursor + header_size,
                    4,
                )
            ):
                raise ValueError("Unsupported KSM import padding")
            name, cursor, _ = self.string(cursor + header_size, end)
            result.append(
                KsmImport(
                    identifier,
                    name,
                    kind,
                    usage & 0xFFFF if header_size == 28 else usage,
                    usage >> 16 if header_size == 28 else None,
                )
            )
        if cursor != end:
            raise ValueError("KSM import count does not match section size")
        return tuple(result)

    def replace_string_constants(self, replacements: dict[int, str]) -> bytes:
        constants = {variable.id: variable for variable in self.constants}
        result = bytearray(self.data)
        for identifier, replacement in replacements.items():
            variable = constants.get(identifier)
            if variable is None or variable.type != KsmValueType.STRING:
                raise ValueError("Edit must reference a known string constant")
            encoded = replacement.encode("utf-8")
            if b"\0" in encoded or len(encoded) + 1 > variable.string_capacity:
                raise ValueError("Replacement exceeds the original constant capacity")
            result[
                variable.value_offset : variable.value_offset + variable.string_capacity
            ] = encoded + bytes(variable.string_capacity - len(encoded))
        return bytes(result)
