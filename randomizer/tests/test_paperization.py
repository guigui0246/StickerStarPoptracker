from collections import Counter
import unittest

from ..integrations.rom.paperization import PaperizationLock, desert_gate_requirements, wiggler_restoration_requirements
from ..standalone.generation import InventoryState


def lock(identifier: str, accepted: tuple[str, ...], map_name: str = "w2_sab_00") -> PaperizationLock:
    return PaperizationLock(identifier, 1, map_name, "GF_TEST", "", accepted, ("init", "before", "after", "cancel"))


class PaperizationTests(unittest.TestCase):
    def test_alternative_tools_and_place_are_independent_requirements(self) -> None:
        puzzle = lock("mooring", ("SL_SCISSORS", "SL_HAIRCUT_SCISSORS"))
        rules = puzzle.requirements({"SL_SCISSORS": "scissors", "SL_HAIRCUT_SCISSORS": "shears"}, "paper", "place")
        self.assertTrue(rules.allows(InventoryState(Counter(("paper", "place", "shears")))))
        self.assertFalse(rules.allows(InventoryState(Counter(("place", "shears")))))
        self.assertFalse(rules.allows(InventoryState(Counter(("paper", "shears")))))

    def test_desert_gate_needs_all_six_slots_not_any_six_variants(self) -> None:
        locks = tuple(lock(f"w2_sab_gate_{index}", (f"SL_{index}",)) for index in range(1, 7))
        rules = desert_gate_requirements(locks, {f"SL_{index}": f"slot{index}" for index in range(1, 7)}, "paper")
        inventory = InventoryState(Counter(("paper", *(f"slot{index}" for index in range(1, 7)))))
        self.assertTrue(rules.allows(inventory))
        inventory.items["slot4"] = 0
        inventory.items["slot1"] = 6
        self.assertFalse(rules.allows(inventory))

    def test_incomplete_puzzle_mapping_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unmapped"):
            lock("windmill", ("SL_FAN",)).requirements({}, "paper")
        with self.assertRaisesRegex(ValueError, "six native slots"):
            desert_gate_requirements((), {}, "paper")

    def test_wiggler_requires_four_distinct_segments_despite_shared_slot_alternatives(self) -> None:
        bodies = tuple(f"PK_HANACHAN_BODY_{index}" for index in range(1, 5))
        locks = tuple(
            PaperizationLock(
                f"w3_tre_02_hanachan_{index}",
                index,
                "w3_tre_02",
                f"GF_W3_TRE_REV_HANACHAN_{index}",
                "",
                bodies,
                ("init", "before", "after", "cancel"),
            )
            for index in range(1, 5)
        )
        mapping = {body: f"body{index}" for index, body in enumerate(bodies, 1)}
        rules = wiggler_restoration_requirements(locks, mapping, "paper")
        self.assertFalse(rules.allows(InventoryState(Counter({"paper": 1, "body1": 4}))))
        self.assertTrue(rules.allows(InventoryState(Counter(("paper", "body1", "body2", "body3", "body4")))))
        with self.assertRaisesRegex(ValueError, "distinct"):
            wiggler_restoration_requirements(locks, {body: "one_body" for body in bodies}, "paper")

    def test_wiggler_rejects_incomplete_native_slots(self) -> None:
        with self.assertRaisesRegex(ValueError, "four observed"):
            wiggler_restoration_requirements((), {}, "paper")
