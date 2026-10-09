from dataclasses import replace
import unittest

from ..integrations.rom.battle_formations import battle_formations
from ..integrations.rom.kdm import KdmArray, KdmDocument, KdmField, KdmPointer, KdmStructure


def fixture() -> KdmDocument:
    document = KdmDocument.__new__(KdmDocument)
    document.structures = {
        21: KdmStructure(21, (3, 8, 8, 8, 8, 8, 3, 3, 3, 1), 32, 4),
        22: KdmStructure(22, (3, 3, 15, 1, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 7, 8, 4, 4), 64, 4),
    }
    unit = ("goomba", 14, 0, 0, 0, 0, "", "", "", 0)
    slots = tuple(KdmField(100 + index * 32, 21, tuple(KdmField(100, 3, value) for value in unit)) for index in range(2))
    row = ("formation", "label", KdmPointer(100, 15), 2, "normal", "first", "after", "NORMAL_BATTLE", "", "", "", "", "", "", False, 100, 18, False, False)
    document.arrays = {
        100: KdmArray(1, 100, 21, 20, slots),
        300: KdmArray(2, 300, 22, 19, (KdmField(300, 22, tuple(KdmField(300, 3, value) for value in row)),)),
    }
    document.tables = {"enemySetDataTable": KdmArray(3, 500, 15, 2, (KdmField(500, 15, KdmPointer(300, 15)), KdmField(504, 15, KdmPointer(0, 15))))}
    return document


class BattleFormationTests(unittest.TestCase):
    def test_duplicate_unit_slots_and_battle_event_are_preserved(self) -> None:
        formation, = battle_formations(fixture())
        self.assertEqual(formation.units, ("goomba", "goomba"))
        self.assertEqual(formation.battle_event, "NORMAL_BATTLE")
        self.assertEqual(formation.maps, ("normal", "first", "after"))

    def test_incorrect_declared_count_is_rejected(self) -> None:
        document = fixture()
        array = document.arrays[300]
        row = array.values[0].value
        assert isinstance(row, tuple)
        document.arrays[300] = replace(array, values=(replace(array.values[0], value=(*row[:3], KdmField(300, 1, 1), *row[4:])),))
        with self.assertRaisesRegex(ValueError, "count"):
            battle_formations(document)

    def test_duplicate_formation_and_internal_sentinel_are_rejected(self) -> None:
        for duplicate in (True, False):
            document = fixture()
            table = document.tables["enemySetDataTable"]
            values = (table.values[0], table.values[0]) if duplicate else tuple(reversed(table.values))
            document.tables["enemySetDataTable"] = replace(table, values=values)
            with self.assertRaises(ValueError):
                battle_formations(document)
