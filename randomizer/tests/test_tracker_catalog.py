from typing import Any, cast
import unittest

from ..data.catalog import parse_catalog
from ..integrations.archipelago.native_catalog import allocate_registry
from ..integrations.archipelago.tracker_catalog import TrackerCatalog
from ..settings import Settings
from . import test_native_ap_catalog


class TrackerCatalogTests(unittest.TestCase):
    def test_default_settings_are_explicit_in_tracker_mapping(self) -> None:
        data, _ = test_native_ap_catalog.fixture()
        game = parse_catalog(data)
        tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64, Settings())
        values = tracker.setting_values()
        self.assertEqual(values["museum"], "all")
        self.assertEqual(values["enemy_rewards"], "on")
        self.assertEqual(values["door_stickers"], "randomized")
        self.assertEqual(values["generic_stickers"], "enabled")
        self.assertEqual(tracker.mappings()["settings"], values)

    def test_mappings_and_predicates_share_stable_ids_and_exclude_fixed_rewards(self) -> None:
        data, _ = test_native_ap_catalog.fixture()
        game = parse_catalog(data)
        tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64)
        definitions = tracker.definitions()
        self.assertEqual(len(cast(Any, definitions)["locations"]), len(game.locations) - len(game.fixed_rewards))
        self.assertEqual(len(cast(Any, tracker.mappings())["items"]), len(game.items) - len(set(game.fixed_rewards.values())))
        for location in game.locations:
            if location.id not in game.fixed_rewards:
                self.assertIn("function " + tracker.access_function(location.id) + "()", tracker.lua())
        self.assertIn('TRACKER_CATALOG_HASH = "' + "a" * 64 + '"', tracker.lua())

    def test_catalog_hash_is_required(self) -> None:
        data, _ = test_native_ap_catalog.fixture()
        game = parse_catalog(data)
        with self.assertRaises(ValueError):
            TrackerCatalog(game, allocate_registry(game), "wrong")
