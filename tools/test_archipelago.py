"""Integration checks against an actual AP checkout, including packaged loading.

Run with Python 3.12 and AP's runtime dependencies available:
python tools/test_archipelago.py --ap-root /path/to/Archipelago-0.6.8
"""

import argparse
import os
from pathlib import Path
import shutil
import sys
import unittest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ap-root", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path)
    args = parser.parse_args()
    root = args.ap_root.resolve()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if args.dependencies:
        sys.path.insert(0, str(args.dependencies.resolve()))
    os.environ["AP_TEST_WORLDS"] = "sticker_star"
    target = root / "custom_worlds" / "sticker_star.apworld"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / "dist" / "sticker_star.apworld", target)
    from Utils import version_tuple

    if tuple(version_tuple) != (0, 6, 8):
        raise RuntimeError(f"Expected AP 0.6.8, got {version_tuple}")
    from BaseClasses import CollectionState
    from Fill import distribute_items_restrictive
    from test.general import setup_multiworld
    from worlds import failed_world_loads
    from worlds.sticker_star.integrations.archipelago.world import StickerStarWorld

    if "sticker_star" in failed_world_loads:
        raise RuntimeError(failed_world_loads["sticker_star"])

    class APTests(unittest.TestCase):
        def test_two_player_generation_and_completion(self) -> None:
            for seed in range(10):
                multiworld = setup_multiworld(
                    [StickerStarWorld, StickerStarWorld], seed=seed
                )
                distribute_items_restrictive(multiworld)
                state = CollectionState(multiworld)
                self.assertFalse(multiworld.has_beaten_game(state))
                remaining = set(multiworld.get_locations())
                while remaining:
                    state.sweep_for_advancements()
                    reachable = [loc for loc in remaining if loc.can_reach(state)]
                    if not reachable:
                        break
                    for loc in reachable:
                        if loc.item:
                            state.collect(loc.item, True, loc)
                        remaining.remove(loc)
                self.assertFalse(remaining)
                self.assertTrue(multiworld.has_beaten_game(state))
                for player in (1, 2):
                    self.assertIsNone(
                        multiworld.get_location("Rescue Toad", player).address
                    )
                    self.assertTrue(
                        multiworld.get_location("Example Victory", player).locked
                    )
                    multiworld.worlds[player].generate_output(str(project / "dist"))

        def test_directional_rule_and_town_gate(self) -> None:
            multiworld = setup_multiworld(StickerStarWorld, seed=42)
            state = CollectionState(multiworld)
            self.assertTrue(state.can_reach("Menu", "Region", 1))
            self.assertTrue(state.can_reach("World 1-1", "Region", 1))
            self.assertFalse(state.can_reach("Decalburg", "Region", 1))
            self.assertFalse(
                multiworld.get_entrance("field_path:1", 1).access_rule(state)
            )
            state.collect(multiworld.worlds[1].create_item("Hammer"), True)
            self.assertTrue(
                multiworld.get_entrance("field_path:1", 1).access_rule(state)
            )
            state.collect(multiworld.worlds[1].create_item("Decalburg Access"), True)
            self.assertTrue(state.can_reach("Decalburg", "Region", 1))

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(APTests)
    )
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
