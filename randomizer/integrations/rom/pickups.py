"""Typed views of item placement records discovered in the real disposition table."""

from dataclasses import dataclass
from .kdm import KdmDocument, KdmField, KdmPointer


@dataclass(frozen=True)
class GamePickup:
    map_name: str
    object_name: str
    item_name: str
    item_field_offset: int
    collection_flag: int
    x: float
    y: float
    z: float

    @property
    def id(self) -> str:
        return f"{self.map_name}/{self.object_name}@{self.item_field_offset:08x}"


def record(field: KdmField, size: int) -> tuple[KdmField, ...]:
    if not isinstance(field.value, tuple) or len(field.value) != size:
        raise ValueError("Unexpected disposition record shape")
    return field.value


def pointer(field: KdmField) -> KdmPointer:
    if not isinstance(field.value, KdmPointer):
        raise ValueError("Expected a disposition array pointer")
    return field.value


def text(field: KdmField) -> str:
    if not isinstance(field.value, str):
        raise ValueError("Expected a disposition name")
    return field.value


def integer(field: KdmField) -> int:
    if type(field.value) is not int:
        raise ValueError("Expected a disposition flag")
    return field.value


def coordinate(field: KdmField) -> float:
    if type(field.value) is not float:
        raise ValueError("Expected a disposition coordinate")
    return field.value


def item_pickups(document: KdmDocument) -> tuple[GamePickup, ...]:
    expected = (3, 3, 15, 0, 0, 0, 0, 4, 1, 15)
    if 39 not in document.structures or document.structures[39].fields != expected:
        raise ValueError("Unsupported item placement schema")
    result: dict[int, GamePickup] = {}
    table = document.tables["all_disposDataTbl"]
    for group_ref in table.values:
        group_pointer = pointer(group_ref)
        if not group_pointer.address:
            continue
        for group in document.pointed_array(group_pointer).values:
            group_fields = record(group, 10)
            maps_pointer = pointer(group_fields[7])
            if not maps_pointer.address:
                continue
            for map_ref in document.pointed_array(maps_pointer).values:
                map_pointer = pointer(map_ref)
                if not map_pointer.address:
                    continue
                for map_row in document.pointed_array(map_pointer).values:
                    map_fields = record(map_row, 3)
                    map_name = text(map_fields[0])
                    items_pointer = pointer(map_fields[1])
                    if not items_pointer.address:
                        continue
                    for item_row in document.pointed_array(items_pointer).values:
                        values = record(item_row, 10)
                        pickup = GamePickup(
                            map_name,
                            text(values[0]),
                            text(values[1]),
                            values[1].offset,
                            integer(values[8]),
                            coordinate(values[3]),
                            coordinate(values[4]),
                            coordinate(values[5]),
                        )
                        previous = result.get(pickup.item_field_offset)
                        if previous and previous != pickup:
                            raise ValueError(
                                "One placement record belongs to conflicting maps"
                            )
                        result[pickup.item_field_offset] = pickup
    return tuple(result.values())
