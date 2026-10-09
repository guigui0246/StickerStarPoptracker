from copy import deepcopy
from collections import Counter
import unittest

from ..data.catalog import Json, parse_catalog
from ..data.native_routes import apply_native_routes
from ..integrations.rom.room_links import RoomLink
from ..standalone.generation import InventoryState, reachable_regions
from .test_native_ap_catalog import fixture


class NativeRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog, _ = fixture()
        self.catalog["paths"] = []
        self.forward = RoomLink(12, 0, 0, 0, "map", "out", "town", "in", "enter", "exit")
        self.reverse = RoomLink(24, 0, 0, 0, "town", "in", "map", "out", "", "")
        self.review: dict[str, Json] = {
            "format_version": 1, "source_sha256": "a" * 64,
            "room_regions": {"map": "menu", "town": "town"},
            "links": {
                self.forward.id: {"requires": {"item": "town"}, "evidence": "Reviewed exit callback"},
                self.reverse.id: {"requires": {"all": []}, "evidence": "Reviewed return callback"},
            },
        }

    def test_directions_are_independent_and_rules_reach_the_shared_model(self) -> None:
        result = apply_native_routes(self.catalog, (self.forward, self.reverse), self.review, "a" * 64)
        game = parse_catalog(result)
        state = InventoryState(Counter())
        self.assertEqual(reachable_regions(game, state), {"menu"})
        state.items["town"] = 1
        self.assertEqual(reachable_regions(game, state), {"menu", "town"})
        self.assertFalse(game.paths[0].reverse.rules.allows(state))
        self.assertTrue(game.paths[1].forward.rules.allows(InventoryState(Counter())))
        self.assertEqual(self.catalog["paths"], [])

    def test_incomplete_or_stale_review_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source link table"):
            apply_native_routes(self.catalog, (self.forward, self.reverse), self.review, "b" * 64)
        with self.assertRaisesRegex(ValueError, "exactly one review"):
            apply_native_routes(self.catalog, (self.forward,), self.review, "a" * 64)

    def test_exclusions_require_a_reason_and_virtual_destinations_are_not_edges(self) -> None:
        virtual = RoomLink(40, 0, 0, 0, "map", "virtual", "null", "null", "", "")
        review = deepcopy(self.review)
        review["links"] = {virtual.id: {"exclude": "Native world-map transition; bound separately"}}
        result = apply_native_routes(self.catalog, (virtual,), review, "a" * 64)
        self.assertEqual(result["paths"], [])
        review["links"] = {virtual.id: {"requires": {"all": []}, "evidence": "No traversal"}}
        with self.assertRaisesRegex(ValueError, "excluded explicitly"):
            apply_native_routes(self.catalog, (virtual,), review, "a" * 64)
