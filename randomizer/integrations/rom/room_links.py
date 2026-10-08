"""Native directed room connections, preserving event callbacks and virtual exits.

These records are evidence for catalog authors, not unconditional logic edges.
An exit callback can impose a puzzle requirement even when its destination exists.
"""

from dataclasses import dataclass

from .kdm import KdmDocument
from .pickups import integer, pointer, record, text


@dataclass(frozen=True)
class RoomLink:
    offset: int
    kind: int
    argument: int
    index: int
    source_room: str
    source_entrance: str
    destination_room: str
    destination_entrance: str
    enter_callback: str
    exit_callback: str

    @property
    def id(self) -> str:
        return f"room_link/{self.source_room}/{self.source_entrance}@{self.offset:08x}"

    @property
    def has_destination(self) -> bool:
        return self.destination_room not in ("", "null") and self.destination_entrance not in ("", "null")


def room_links(document: KdmDocument) -> tuple[RoomLink, ...]:
    """Read the named production link table rather than unrelated array shapes."""
    schema = document.structures.get(21)
    group_schema = document.structures.get(22)
    if (schema is None or schema.fields != (1, 1, 1, 3, 3, 3, 3, 3, 3)
            or group_schema is None or group_schema.fields != (3, 20, 1)):
        raise ValueError("Unsupported native room-link schema")
    table = document.tables.get("link_data_all")
    if table is None or table.type_id != 15:
        raise ValueError("Missing native room-link table")
    result: list[RoomLink] = []
    seen: set[int] = set()
    for reference in table.values:
        group_array = document.pointed_array(pointer(reference))
        if group_array.type_id != 22 or len(group_array.values) != 1:
            raise ValueError("Room-link table must reference native room groups")
        group = record(group_array.values[0], 3)
        entries = document.pointed_array(pointer(group[1]))
        if entries.type_id != 15 or integer(group[2]) != len(entries.values):
            raise ValueError("Room-link group count does not match its entries")
        for entry in entries.values:
            target = document.pointed_array(pointer(entry))
            if target.type_id != 21 or len(target.values) != 1:
                raise ValueError("Room-link group must reference individual native records")
            row = record(target.values[0], 9)
            if row[0].offset in seen:
                raise ValueError("Duplicate native room-link reference")
            seen.add(row[0].offset)
            link = RoomLink(row[0].offset, integer(row[0]), integer(row[1]), integer(row[2]),
                            text(row[3]), text(row[4]), text(row[5]), text(row[6]),
                            text(row[7]), text(row[8]))
            if link.source_room != text(group[0]) or not link.source_entrance:
                raise ValueError("Room link lacks a matching source identity")
            result.append(link)
    return tuple(result)
