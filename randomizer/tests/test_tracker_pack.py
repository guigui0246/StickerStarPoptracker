"""Validate loadable catalog pack contents without emitting an artifact."""

import json
import unittest
from dataclasses import replace
from xml.etree import ElementTree

from ..data.catalog import parse_catalog
from ..domain import Location
from ..integrations.archipelago.native_catalog import allocate_registry
from ..integrations.archipelago.tracker_catalog import TrackerCatalog
from ..integrations.archipelago.tracker_pack import pack_files
from .test_native_ap_catalog import fixture


class TrackerPackTests(unittest.TestCase):
    def test_large_regions_are_paginated_without_losing_stable_markers(self) -> None:
        data, _ = fixture()
        game = parse_catalog(data)
        extra = tuple(Location(f"extra_{index}", f"Extra {index}", "town") for index in range(40))
        game = replace(game, locations=game.locations + extra, pool=game.pool + ("coins",) * len(extra))
        tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64)
        files = pack_files(tracker)
        maps = json.loads(files["maps/maps.json"])
        locations = json.loads(files["locations/locations.json"])
        self.assertEqual(len(locations), len(game.locations) - len(game.fixed_rewards))
        self.assertGreater(len(maps), 2)
        for row in maps:
            self.assertLessEqual(int(ElementTree.fromstring(files[row["img"]]).attrib["height"]), 612)
        for location in extra:
            self.assertEqual(sum("@" + row["name"] + "/Check" == tracker.location_code(location.id) for row in locations), 1)

    def test_precollected_variants_do_not_overwrite_each_others_pack_identity(self) -> None:
        data, _ = fixture()
        game = parse_catalog(data)
        registry = allocate_registry(game)
        first = pack_files(TrackerCatalog(game, registry, "a" * 64))
        second = pack_files(TrackerCatalog(replace(game, starting_items=("hammer",)), registry, "a" * 64))
        self.assertNotEqual(
            json.loads(first["manifest.json"])["package_uid"], json.loads(second["manifest.json"])["package_uid"]
        )

    def test_every_mapping_has_a_marker_and_every_asset_is_self_contained(self) -> None:
        data, _ = fixture()
        game = parse_catalog(data)
        tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64)
        files = pack_files(tracker)
        items = json.loads(files["items/items.json"])
        locations = json.loads(files["locations/locations.json"])
        maps = json.loads(files["maps/maps.json"])
        codes = {"@" + row["name"] + "/Check" for row in locations}
        for location in game.locations:
            if location.id not in game.fixed_rewards:
                self.assertIn(tracker.location_code(location.id), codes)
        self.assertEqual(len(locations), len(game.locations) - len(game.fixed_rewards))
        for row in items + maps:
            self.assertIn(row["img"], files)
        for name, content in files.items():
            if name.endswith(".svg"):
                ElementTree.fromstring(content)
        map_names = {row["name"] for row in maps}
        for location in locations:
            self.assertIn(location["map_locations"][0]["map"], map_names)
        self.assertIn('Tracker:AddLocations("locations/locations.json")', files["scripts/init.lua"])

    def test_names_are_escaped_in_schematic_maps(self) -> None:
        data, _ = fixture()
        data["regions"][1]["name"] = 'Town <&> "square"'
        game = parse_catalog(data)
        files = pack_files(TrackerCatalog(game, allocate_registry(game), "a" * 64))
        document = ElementTree.fromstring(files["images/region_1.svg"])
        text = document.find("{http://www.w3.org/2000/svg}text")
        self.assertIsNotNone(text)
        assert text is not None
        self.assertEqual(text.text, 'Town <&> "square"')
