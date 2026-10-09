"""Exact enemy formations; table presence alone does not prove encounter access."""

from dataclasses import dataclass

from .kdm import KdmDocument
from .pickups import integer, pointer, record, text


@dataclass(frozen=True)
class BattleFormation:
    id: str
    units: tuple[str, ...]
    battle_event: str
    maps: tuple[str, str, str]


def battle_formations(document: KdmDocument) -> tuple[BattleFormation, ...]:
    schemas = {
        21: (3, 8, 8, 8, 8, 8, 3, 3, 3, 1),
        22: (3, 3, 15, 1, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 7, 8, 4, 4),
    }
    if any(identifier not in document.structures or document.structures[identifier].fields != fields
           for identifier, fields in schemas.items()):
        raise ValueError("Unsupported native battle formation schema")
    table = document.tables.get("enemySetDataTable")
    if table is None or table.type_id != 15:
        raise ValueError("Missing native enemy formation table")
    result = []
    seen = set()
    for index, reference in enumerate(table.values):
        target = pointer(reference)
        if not target.address:
            if index != len(table.values) - 1:
                raise ValueError("Battle formation sentinel must be last")
            continue
        array = document.pointed_array(target)
        if array.type_id != 22 or len(array.values) != 1:
            raise ValueError("Battle table must reference individual formations")
        row = record(array.values[0], 19)
        identifier = text(row[0])
        if not identifier or identifier in seen:
            raise ValueError("Duplicate or empty battle formation identity")
        seen.add(identifier)
        entries = document.pointed_array(pointer(row[2]))
        if entries.type_id != 21:
            raise ValueError("Battle formation must contain native unit slots")
        units = tuple(text(record(unit, 10)[0]) for unit in entries.values
                      if text(record(unit, 10)[0]))
        if integer(row[3]) != len(units):
            raise ValueError("Battle formation count does not match unit slots")
        result.append(BattleFormation(identifier, units, text(row[7]),
                                     (text(row[4]), text(row[5]), text(row[6]))))
    return tuple(result)
