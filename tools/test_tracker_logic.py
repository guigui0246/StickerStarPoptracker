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

    def test_each_level_has_an_independent_visible_door_unlock(self) -> None:
        stages = {p.stem for p in (ROOT / "locations").glob("w*.json")}
        expected = {"door_place_" + stage for stage in stages}
        actual = {c for c in self.codes if c.startswith("door_place_")}
        self.assertEqual(actual, expected)
        grids = json.loads((ROOT / "layouts/item_grids.json").read_text())
        visible: set[str] = set()
        for world in range(1, 7):
            for row in grids[f"w{world}_door_grid"]["content"][0]["rows"]:
                visible.update(row)
        self.assertEqual(visible, expected)
        for stage in stages:
            function = "DOOR_" + stage.upper()
            needed = ["paperization", "sticker_secret_door",
                      "door_place_" + stage]
            self.assertTrue(self.can(function, *needed))
            self.assertFalse(self.can(function, *needed[:2]))
            wrong_door = next(code for code in expected if code != needed[2])
            self.assertFalse(self.can(function, *needed[:2], wrong_door))

    def test_towns_are_registered_loaded_and_visible(self) -> None:
        maps = json.loads((ROOT / "maps/maps.json").read_text())
        map_names = {m["name"] for m in maps}
        tabs = json.loads((ROOT / "layouts/tabs.json").read_text())
        loader = (ROOT / "scripts/locations.lua").read_text()
        for town in ("decalburg", "surfshine_harbor"):
            self.assertIn(town, map_names)
            self.assertIn(f'locations/{town}.json', loader)
            self.assertTrue(any(
                town in tab["content"].get("maps", [])
                for tab in tabs["map_tabs"]["tabs"]
            ))
            data = json.loads((ROOT / f"locations/{town}.json").read_text())
            self.assertTrue(data[0]["children"])

    def test_album_modes_and_upgrades_are_independent_rewards(self) -> None:
        by_code = {item["codes"]: item for item in self.items}
        mode = by_code["album_mode"]
        self.assertEqual(mode["type"], "progressive")
        self.assertEqual(mode["initial_stage_idx"], 0)
        self.assertEqual(
            [stage["codes"] for stage in mode["stages"]],
            ["album_all_at_start", "album_randomized", "album_infinite"],
        )
        self.assertTrue(all(
            stage["inherit_codes"] is False for stage in mode["stages"]
        ))
        upgrades = {
            f"album_page_upgrade_{number}" for number in range(1, 7)
        }
        self.assertEqual(
            {code for code in self.codes if
             code.startswith("album_page_upgrade_")}, upgrades,
        )
        for code in upgrades:
            self.assertEqual(by_code[code]["type"], "toggle")
        grids = json.loads((ROOT / "layouts/item_grids.json").read_text())
        visible = {
            code
            for grid in grids["album_pages_grid"]["content"]
            for row in grid["rows"]
            for code in row
        }
        self.assertEqual(visible, upgrades | {"album_mode"})


if __name__ == "__main__":
    unittest.main()
