"""Exact paperization puzzle inputs from the native lock table.

Accepted inputs are alternatives for one lock. Separate locks remain separate
requirements; six matching pictures on the desert gate are six simultaneous
locks, not one alternative. Traversal effects must be bound explicitly.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ...domain import Rules
from .kdm import KdmDocument
from .pickups import integer, pointer, record, text


@dataclass(frozen=True)
class PaperizationLock:
    id: str
    number: int
    map_name: str
    completion_flag: str
    key_item: str
    accepted_items: tuple[str, ...]
    callbacks: tuple[str, str, str, str]

    def requirements(self, items: Mapping[str, str], paperization: str, place_item: str | None = None) -> Rules:
        """Resolve native inputs to catalog IDs, rejecting incomplete mappings."""
        missing = set(self.accepted_items) - items.keys()
        if missing:
            raise ValueError(f"Unmapped puzzle inputs for {self.id}: {sorted(missing)}")
        if not self.accepted_items:
            raise ValueError(f"Puzzle {self.id} has no observed accepted inputs")
        inputs = Rules.any_of(*(Rules.has(items[item]) for item in self.accepted_items))
        return Rules.all_of(Rules.has(paperization), inputs, *((Rules.has(place_item),) if place_item else ()))


def paperization_locks(document: KdmDocument) -> tuple[PaperizationLock, ...]:
    schema = document.structures.get(21)
    if (
        schema is None
        or len(schema.fields) != 72
        or schema.fields[11] != 3
        or schema.fields[40:48] != (3,) * 8
        or schema.fields[57] != 3
        or schema.fields[60:] != (3,) * 12
    ):
        raise ValueError("Unsupported paperization lock schema")
    table = document.tables.get("lockDataTable")
    if table is None or table.type_id != 15:
        raise ValueError("Missing native paperization lock table")
    result: list[PaperizationLock] = []
    seen: set[str] = set()
    numbers: set[int] = set()
    for index, reference in enumerate(table.values):
        target = pointer(reference)
        if not target.address:
            if index != len(table.values) - 1:
                raise ValueError("Paperization sentinel must be last")
            continue
        array = document.pointed_array(target)
        if array.type_id != 21 or len(array.values) != 1:
            raise ValueError("Paperization table must reference individual locks")
        row = record(array.values[0], 72)
        identifier, number = text(row[0]), integer(row[1])
        if not identifier or identifier in seen or number in numbers or number <= 0:
            raise ValueError("Duplicate or invalid paperization lock identity")
        seen.add(identifier)
        numbers.add(number)
        result.append(
            PaperizationLock(
                identifier,
                number,
                text(row[11]),
                text(row[44]),
                text(row[57]),
                tuple(dict.fromkeys(text(field) for field in row[60:] if text(field))),
                (text(row[40]), text(row[41]), text(row[42]), text(row[43])),
            )
        )
    return tuple(result)


def desert_gate_requirements(locks: tuple[PaperizationLock, ...], items: Mapping[str, str], paperization: str) -> Rules:
    """The six-lock bigdoor_check in w2_sab_00 requires every native slot."""
    by_id = {lock.id: lock for lock in locks}
    names = tuple(f"w2_sab_gate_{index}" for index in range(1, 7))
    if any(name not in by_id or by_id[name].map_name != "w2_sab_00" for name in names):
        raise ValueError("Desert gate does not match the inspected six native slots")
    return Rules.all_of(*(by_id[name].requirements(items, paperization) for name in names))


def wiggler_restoration_requirements(
    locks: tuple[PaperizationLock, ...], items: Mapping[str, str], paperization: str
) -> Rules:
    """All four distinct segments are consumed by the four restoration slots.

    Each slot accepts any segment, so combining four independent alternatives
    would incorrectly allow one received segment to satisfy every slot.
    """
    bodies = tuple(f"PK_HANACHAN_BODY_{index}" for index in range(1, 5))
    by_id = {lock.id: lock for lock in locks}
    for index in range(1, 5):
        lock = by_id.get(f"w3_tre_02_hanachan_{index}")
        if (
            lock is None
            or lock.map_name != "w3_tre_02"
            or set(lock.accepted_items) != set(bodies)
            or lock.completion_flag.lower() != f"gf_w3_tre_rev_hanachan_{index}"
        ):
            raise ValueError("Wiggler restoration does not match the four observed native slots")
    if set(bodies) - items.keys() or len({items[body] for body in bodies}) != 4:
        raise ValueError("Wiggler restoration requires four distinct mapped segment items")
    return Rules.all_of(Rules.has(paperization), *(Rules.has(items[body]) for body in bodies))
