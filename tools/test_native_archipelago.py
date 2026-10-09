"""Exercise packaged native generation against the actual AP 0.6.8 runtime.

Uses an explicitly artificial rules fixture with observed native source IDs.
This verifies the adapter and recipes, not the full game's puzzle logic.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ap-root", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path)
    parser.add_argument("--rom", type=Path, required=True)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project))
    from randomizer.tests.test_native_ap_catalog import fixture

    catalog, bindings = fixture()
    dist = project / "dist/native-ap-generation-test"
    dist.mkdir(parents=True, exist_ok=True)
    catalog_path, bindings_path = dist / "catalog.json", dist / "bindings.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    bindings_path.write_text(json.dumps(bindings), encoding="utf-8")
    package = dist / "sticker_star.apworld"
    subprocess.run(
        [
            sys.executable,
            str(project / "tools/build_apworld.py"),
            "--output",
            str(package),
            "--catalog",
            str(catalog_path),
            "--bindings",
            str(bindings_path),
            "--rom",
            str(args.rom),
        ],
        check=True,
    )
    root = args.ap_root.resolve()
    target = root / "custom_worlds/sticker_star.apworld"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(package, target)
    sys.path.insert(0, str(root))
    if args.dependencies:
        sys.path.insert(0, str(args.dependencies.resolve()))
    os.environ["AP_TEST_WORLDS"] = "sticker_star"
    from Utils import version_tuple  # pyright: ignore[reportMissingImports]

    if tuple(version_tuple) != (0, 6, 8):
        raise RuntimeError("Native integration tests require AP 0.6.8")
    from BaseClasses import CollectionState  # pyright: ignore[reportMissingImports]
    from Fill import distribute_items_restrictive  # pyright: ignore[reportMissingImports]
    from test.general import setup_multiworld  # pyright: ignore[reportMissingImports]
    from worlds.sticker_star import StickerStarWorld  # pyright: ignore[reportMissingImports]
    from worlds.sticker_star.integrations.rom.native_recipe import (  # pyright: ignore[reportMissingImports]
        decode_native_recipe,
    )
    from worlds.sticker_star.integrations.rom.native_delivery import NativeRewardKind  # pyright: ignore[reportMissingImports]

    class NativeAPTests(unittest.TestCase):
        def verify(self, multiworld) -> None:
            distribute_items_restrictive(multiworld)
            state = CollectionState(multiworld)
            remaining = set(multiworld.get_locations())
            while remaining:
                state.sweep_for_advancements()
                accessible = [location for location in remaining if location.can_reach(state)]
                if not accessible:
                    break
                for location in accessible:
                    if location.item:
                        state.collect(location.item, True, location)
                    remaining.remove(location)
            self.assertFalse(remaining)
            self.assertTrue(multiworld.has_beaten_game(state))
            for player in multiworld.player_ids:
                world = multiworld.worlds[player]
                world.generate_output(str(dist))
                stem = dist / multiworld.get_out_file_name_base(player)
                recipe = decode_native_recipe(Path(str(stem) + ".stickerpatch").read_bytes())
                config = json.loads(Path(str(stem) + ".client.json").read_text(encoding="utf-8"))
                tracker = json.loads(Path(str(stem) + ".tracker.json").read_text(encoding="utf-8"))
                self.assertEqual(tracker["tracker"], world.fill_slot_data()["tracker"])
                self.assertEqual(
                    set(tracker["tracker"]["locations"]), {str(identifier) for identifier in config["locations"].values()}
                )
                self.assertEqual(len(tracker["locations"]), len(config["locations"]))
                self.assertIn(tracker["catalog_hash"], Path(str(stem) + ".tracker.lua").read_text(encoding="utf-8"))
                self.assertEqual(recipe.plan.remote_session.slot, player)
                self.assertEqual(recipe.plan.fingerprint.hex(), config["save_seed_fingerprint"])
                self.assertEqual(world.fill_slot_data()["catalog_hash"], recipe.plan.remote_session.catalog_hash)
                self.assertEqual(len(recipe.plan.checks), len(world.definition.locations))
                self.assertEqual(recipe.plan.checks[-1].reward.kind, NativeRewardKind.VICTORY)
                self.assertLessEqual(len(recipe.plan.flags), 1114)
                local = {row["location"]: row for row in config["local_rewards"]}
                for location in world.definition.locations:
                    if location.id in world.definition.fixed_rewards:
                        continue
                    placed = multiworld.get_location(location.name, player).item
                    identifier = world.location_name_to_id[location.name]
                    self.assertEqual(identifier in local, placed.player == player)
                    if placed.player == player:
                        self.assertEqual(local[identifier]["item"], placed.code)
                        self.assertNotIn(world.bindings.locations[location.id].id, config["remote_placements"])
                    else:
                        description = config["remote_placements"][world.bindings.locations[location.id].id]
                        self.assertEqual(description["item"], placed.name)
                        self.assertEqual(description["player"], placed.player)
                        self.assertEqual(description["location_name"], location.name)
                        self.assertEqual(description["player_name"], multiworld.player_name[placed.player])

        def test_packaged_two_player_generation_produces_native_recipes(self) -> None:
            for seed in range(10):
                self.verify(setup_multiworld([StickerStarWorld, StickerStarWorld], seed=seed))

        def test_settings_share_the_typed_check_pool(self) -> None:
            world = setup_multiworld(StickerStarWorld, seed=42, options={"banners": "off", "album_pages": "randomized"})
            self.assertFalse(any(location.id == "banner" for location in world.worlds[1].definition.locations))
            self.assertEqual(world.worlds[1].definition.pool.count("page"), 6)
            self.verify(world)

        def test_precollected_page_has_priority_receipts_and_an_echo_selector(self) -> None:
            world = setup_multiworld(StickerStarWorld, seed=321, options={"album_pages": "randomized"})
            native = world.worlds[1]
            world.push_precollected(native.create_item("Album Page"))
            world.itempool.remove(next(item for item in world.itempool if item.name == "Album Page"))
            world.itempool.append(native.create_item("25 Coins"))
            self.verify(world)
            plan = native.native_plan()
            self.assertTrue(plan.priority_pages)
            self.assertEqual(len(plan.saved_bytes), 29)
            self.assertEqual(len(plan.remote_page_flags), 6)
            self.assertEqual(plan.starting_item_ids, (native.item_name_to_id["Album Page"],))

        def test_precollected_native_items_have_echo_receipts(self) -> None:
            world = setup_multiworld(StickerStarWorld, seed=123)
            native = world.worlds[1]
            hammer = native.create_item("Hammer")
            world.push_precollected(hammer)
            world.itempool.remove(next(item for item in world.itempool if item.name == "Hammer"))
            world.itempool.append(native.create_item("25 Coins"))
            self.verify(world)
            plan = native.native_plan()
            self.assertEqual(plan.starting_item_ids, (native.item_name_to_id["Hammer"],))
            self.assertEqual(plan.starting_rewards[0].kind, NativeRewardKind.ABILITY)

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeAPTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
