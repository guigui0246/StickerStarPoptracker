"""Editable production logic must retain the exact native source contracts."""

from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ..data.catalog import encode_catalog, load_catalog, load_catalog_data, parse_catalog
from ..data.example import example_game
from ..domain import EndGoal, Event, Goal, Item, Location, Path as WorldPath, Region, Rules, StartingRegion, Vector
from ..integrations.rom.native_generation import NativeBindings, catalog_digest
from ..standalone.__main__ import main

GAME = Path(__file__).resolve().parents[1] / "data" / "game"


class EditableGameCatalogTests(unittest.TestCase):
    def test_python_objects_are_the_authoritative_generation_input(self) -> None:
        from ..data.game import LOCATIONS

        edited = (replace(LOCATIONS[0], rules=Rules.has("ability/hammer")), *LOCATIONS[1:])
        with patch("randomizer.data.game.LOCATIONS", edited):
            game = load_catalog(GAME)
            self.assertIs(game.locations, edited)
            self.assertEqual(load_catalog_data(GAME)["locations"], encode_catalog(game)["locations"])
        self.assertTrue(all(isinstance(item, Item) for item in game.items))
        self.assertTrue(all(isinstance(location, Location) for location in game.locations))
        self.assertTrue(all(isinstance(region, Region) for region in game.regions))
        self.assertEqual(sum(isinstance(region, StartingRegion) for region in game.regions), 1)
        self.assertEqual(sum(isinstance(location, EndGoal) for location in game.locations), 1)
        self.assertTrue(all(isinstance(path, WorldPath) and isinstance(path.forward, Vector)
                            and isinstance(path.reverse, Vector) for path in game.paths))

    def test_interchange_roundtrip_preserves_fixed_class_semantics(self) -> None:
        game = example_game()
        decoded = parse_catalog(encode_catalog(game))
        self.assertEqual(decoded, game)
        self.assertTrue(any(isinstance(item, Event) for item in decoded.items))
        self.assertTrue(any(type(location) is Goal for location in decoded.locations))
        self.assertTrue(any(isinstance(location, EndGoal) for location in decoded.locations))
        self.assertNotEqual(decoded.paths[0].forward.rules, decoded.paths[0].reverse.rules)

    def test_production_registry_and_logic_only_rebinding(self) -> None:
        data = load_catalog_data(GAME)
        game = parse_catalog(data)
        bound = NativeBindings.load(GAME, data)
        self.assertEqual(len(game.locations), 416)
        self.assertEqual(len(game.items), 497)
        edited = deepcopy(data)
        locations = edited["locations"]
        assert isinstance(locations, list) and isinstance(locations[0], dict)
        locations[0]["requires"] = {"item": "ability/hammer"}
        rebound = NativeBindings.load(GAME, edited)
        self.assertEqual(rebound.catalog_hash, catalog_digest(edited))
        self.assertNotEqual(rebound.catalog_hash, bound.catalog_hash)
        self.assertEqual(rebound.locations, bound.locations)
        self.assertEqual(parse_catalog(edited).locations[0].rules, Rules.has("ability/hammer"))

    def test_changed_native_identity_is_rejected(self) -> None:
        data = deepcopy(load_catalog_data(GAME))
        items = data["items"]
        assert isinstance(items, list) and isinstance(items[0], dict)
        items[0]["id"] = "unknown-new-native-item"
        with self.assertRaises(ValueError):
            NativeBindings.load(GAME, data)

    def test_shipped_bindings_digest_is_checked_before_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            original = load_catalog_data(GAME / "native_reference.json")
            raw = load_catalog_data(GAME / "bindings.json")
            raw["catalog_sha256"] = "0" * 64
            (folder / "native_reference.json").write_text(json.dumps(original), encoding="utf-8")
            (folder / "bindings.json").write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different logic catalog"):
                NativeBindings.load(folder, original)

    def test_catalog_command_automatically_selects_editable_directory(self) -> None:
        with patch("randomizer.patch.main") as native, \
                patch("randomizer.standalone.__main__.copy_patch_report"), redirect_stdout(StringIO()):
            main(["--logic", "catalog", "game.3ds", "--seed", "editable-test"])
        arguments = native.call_args_list[0].args[0]
        self.assertEqual(Path(arguments[arguments.index("--catalog") + 1]), GAME)
        self.assertEqual(Path(arguments[arguments.index("--bindings") + 1]), GAME)
        self.assertIn("--open-ground-routes", arguments)
