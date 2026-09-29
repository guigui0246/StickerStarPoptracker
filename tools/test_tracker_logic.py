import json
import unittest
from collections import Counter
from pathlib import Path
import sys
from typing import Any, ClassVar

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from randomizer.core import requirement_met, requirement_items  # noqa: E402
from render_tracker_logic import render  # noqa: E402


class TrackerLogicTests(unittest.TestCase):
    model: ClassVar[dict[str, dict[str, Any]]]
    items: ClassVar[list[dict[str, Any]]]
    codes: ClassVar[set[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.model = json.loads(
            (ROOT / "scripts/randomizer_logic.json").read_text()
        )
        cls.items = json.loads((ROOT / "items/items.json").read_text())
        cls.codes = {i["codes"] for i in cls.items}

    def can(self, function: str, *items: str) -> bool:
        return requirement_met(self.model[function], Counter(items))

    def test_received_star_opens_destination_without_source_clear(
        self,
    ) -> None:
        self.assertFalse(self.can("ACCESS_W1_2"))
        self.assertFalse(self.can("ACCESS_W1_2", "clear_w1_1"))
        self.assertTrue(self.can("ACCESS_W1_2", "star_w1_1"))
        self.assertFalse(any(c.startswith("clear_") for c in self.codes))

    def test_alternate_exits_and_branches(self) -> None:
        self.assertTrue(self.can("ACCESS_W1_6", "star_w1_4"))
        self.assertTrue(self.can("ACCESS_W1_6", "star_w1_5"))
        self.assertFalse(self.can("ACCESS_W3_7", "star_w3_6"))
        self.assertTrue(self.can("ACCESS_W3_7", "star_w3_3_left"))
        self.assertTrue(self.can("ACCESS_W3_7", "star_w3_10"))

    def test_entrance_override_is_separate(self) -> None:
        self.assertFalse(self.can("ACCESS_W4_1", "royal_w3"))
        self.assertTrue(self.can("ACCESS_W4_1", "access_w4_1"))
        self.assertTrue(self.can("ACCESS_W1_1"))
        self.assertTrue(self.can("ACCESS_W3_1"))

    def test_museum_checks_do_not_grant_shop_unlocks(self) -> None:
        self.assertFalse(
            self.can(
                "W1_SECRET",
                "paperization",
                "museum_secret_door",
                "door_place_w1_2",
            )
        )
        self.assertTrue(
            self.can(
                "W1_SECRET",
                "paperization",
                "sticker_secret_door",
                "door_place_w1_2",
            )
        )
        self.assertFalse(
            self.can("W1_SECRET", "paperization", "sticker_secret_door")
        )

    def test_boss_unlock_is_not_a_royal_or_recommended_tool(self) -> None:
        base = ["paperization", "scrap_block_switch"]
        self.assertFalse(
            self.can("W1_FORTRESS", *base, "royal_w1", "req_thing_scissors")
        )
        self.assertTrue(self.can("W1_FORTRESS", *base, "boss_unlock_w1"))
        self.assertTrue(self.can("W6_FINAL", "boss_unlock_w6"))

    def test_all_logic_references_exist_and_lua_matches(self) -> None:
        for name, rule in self.model.items():
            self.assertFalse(requirement_items(rule) - self.codes, name)
        self.assertEqual(
            (ROOT / "scripts/logic.lua").read_text(), render(self.model)
        )


if __name__ == "__main__":
    unittest.main()
