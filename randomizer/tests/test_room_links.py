import unittest

from ..integrations.rom.kdm import KdmArray, KdmDocument, KdmField, KdmPointer, KdmStructure
from ..integrations.rom.room_links import room_links


def fixture() -> KdmDocument:
    document = KdmDocument.__new__(KdmDocument)
    document.structures = {21: KdmStructure(21, (1, 1, 1, 3, 3, 3, 3, 3, 3), 36, 4),
                           22: KdmStructure(22, (3, 20, 1), 12, 4)}
    values = (2, 0, 0, "room_a", "door_01", "room_b", "af_s_bero", "enter_a", "exit_a")
    row = tuple(KdmField(100 + index * 4, 1 if index < 3 else 3, value)
                for index, value in enumerate(values))
    document.arrays = {
        100: KdmArray(1, 100, 21, 9, (KdmField(100, 21, row),)),
        200: KdmArray(2, 200, 15, 1, (KdmField(200, 15, KdmPointer(100, 15)),)),
        300: KdmArray(3, 300, 22, 3, (KdmField(300, 22, (
            KdmField(300, 3, "room_a"), KdmField(304, 20, KdmPointer(200, 20)), KdmField(308, 1, 1))),))}
    document.tables = {"link_data_all": KdmArray(4, 400, 15, 1, (
        KdmField(400, 15, KdmPointer(300, 15)),))}
    return document


class RoomLinksTests(unittest.TestCase):
    def test_direction_and_callbacks_are_preserved_without_inventing_reverse_edge(self) -> None:
        links = room_links(fixture())
        self.assertEqual(len(links), 1)
        self.assertEqual((links[0].source_room, links[0].destination_room), ("room_a", "room_b"))
        self.assertEqual((links[0].enter_callback, links[0].exit_callback), ("enter_a", "exit_a"))
        self.assertTrue(links[0].has_destination)

    def test_duplicate_references_are_rejected(self) -> None:
        document = fixture()
        table = document.tables["link_data_all"]
        document.tables["link_data_all"] = KdmArray(table.id, table.address, 15, 2, table.values * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            room_links(document)

    def test_wrong_group_count_is_rejected(self) -> None:
        document = fixture()
        row = document.arrays[300].values[0].value
        assert isinstance(row, tuple)
        document.arrays[300] = KdmArray(3, 300, 22, 3, (
            KdmField(300, 22, (*row[:2], KdmField(308, 1, 2))),))
        with self.assertRaisesRegex(ValueError, "count"):
            room_links(document)

    def test_virtual_exit_is_retained(self) -> None:
        document = fixture()
        row = document.arrays[100].values[0].value
        assert isinstance(row, tuple)
        changed = tuple(KdmField(field.offset, field.type_id, "null" if index in (5, 6) else field.value)
                        for index, field in enumerate(row))
        document.arrays[100] = KdmArray(1, 100, 21, 9, (KdmField(100, 21, changed),))
        self.assertFalse(room_links(document)[0].has_destination)
