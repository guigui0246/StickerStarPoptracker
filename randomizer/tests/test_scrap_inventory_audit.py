from typing import Any, cast
from dataclasses import replace
import unittest

from ..integrations.rom.kdm import KdmArray, KdmDocument, KdmField, KdmPointer, KdmStructure
from ..integrations.rom.scraps import audit_scrap_inventory
from .test_peels import fixture as peel_fixture


def item_fixture(names):
    document = KdmDocument.__new__(KdmDocument)
    document.structures = {29: KdmStructure(29, (3, 15, 3, 0), 16, 4)}
    fields = (
        KdmField(100, 3, "PK_FIELD_PART"),
        KdmField(104, 15, KdmPointer(0, 15)),
        KdmField(108, 3, "PK_PART"),
        KdmField(112, 0, 1.0),
    )
    document.arrays = {100: KdmArray(1, 100, 29, 4, (KdmField(100, 29, fields),))}
    for index, name in enumerate(names):
        address = 200 + index * 100
        values = tuple(
            KdmField(address + part * 4, 3 if part == 0 else 1, name if part == 0 else 3 if part == 18 else 0)
            for part in range(19)
        )
        document.arrays[address] = KdmArray(index + 2, address, 30, 19, (KdmField(address, 30, values),))
    return document


class ScrapInventoryAuditTests(unittest.TestCase):
    def test_restoration_variants_are_evidence_not_additional_pickup_checks(self):
        puzzles = peel_fixture()
        row = puzzles.arrays[100].values[0]
        fields = list(cast(Any, row).value)
        fields[60] = replace(fields[60], value="PK_REPAIR")
        puzzles.arrays[100] = replace(puzzles.arrays[100], values=(replace(row, value=tuple(fields)),))
        result = audit_scrap_inventory(item_fixture(("PK_PART", "PK_PIECE_0", "PK_REPAIR", "PK_UNKNOWN")), puzzles)
        self.assertEqual(result.field_rewards, ("PK_PART",))
        self.assertEqual(result.peeled_rewards, ("PK_PIECE_0",))
        self.assertEqual(result.restoration_inputs, (("PK_PIECE_0", "PK_REPAIR"),))
        self.assertEqual(result.unclassified, ("PK_UNKNOWN",))

    def test_missing_native_inventory_descriptors_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing inventory"):
            audit_scrap_inventory(item_fixture(("PK_PART",)), peel_fixture())
