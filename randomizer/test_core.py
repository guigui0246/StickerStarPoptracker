import copy
import unittest
from typing import Any
from collections import Counter
from .core import (
    Settings,
    RewardState,
    enabled_checks,
    generate,
    playthrough,
    requirement_met,
    validate_catalog,
)


def fixture() -> dict[str, Any]:
    # Synthetic test catalog, not the game's full routes.
    return {
        "items": {
            "hammer": {"kind": "hammer"},
            "paperization": {"kind": "paperization"},
            "star_1_1_exit": {"kind": "mini_star"},
            "door_place_1_2": {"kind": "door_place"},
            "door_sticker": {
                "kind": "generic_sticker",
                "sticker": "secret_door",
            },
            "fan": {"kind": "thing", "sticker": "fan"},
            "royal_1": {"kind": "royal"},
            "boss_1": {"kind": "boss_unlock"},
            "bridge": {"kind": "scrap"},
            "coins": {"kind": "coins", "amount": 20},
            "door_copy": {"kind": "sticker_copy", "sticker": "secret_door"},
        },
        "starting_items": [],
        "progression_pool": [
            "hammer",
            "paperization",
            "star_1_1_exit",
            "door_place_1_2",
            "door_sticker",
            "fan",
            "royal_1",
            "boss_1",
            "bridge",
        ],
        "filler_pool": ["coins", "door_copy"],
        "checks": [
            {"id": "enemy_goomba", "kind": "enemy"},
            {"id": "shop_toad", "kind": "shop"},
            {"id": "thing_pickup", "kind": "thing"},
            {"id": "scrap_pickup", "kind": "scrap"},
            {"id": "kamek", "kind": "kamek"},
            {"id": "museum_jump", "kind": "museum"},
            {"id": "museum_fan", "kind": "museum"},
            {"id": "star_pickup", "kind": "mini_star"},
            {
                "id": "boss_reward",
                "kind": "boss",
                "requires": {"item": "boss_1"},
            },
            {
                "id": "stage_1_2",
                "kind": "mini_star",
                "requires": {"item": "star_1_1_exit"},
            },
            {
                "id": "door",
                "kind": "thing",
                "requires": {
                    "all": [
                        {"item": "paperization"},
                        {"item": "door_place_1_2"},
                        {"item": "door_sticker"},
                    ]
                },
            },
            {"id": "excellent", "kind": "banner", "threshold": 200},
        ],
        "goal": {
            "all": [
                {"item": "royal_1"},
                {"item": "bridge"},
                {"item": "fan"},
                {"item": "hammer"},
            ]
        },
    }


class SeedTests(unittest.TestCase):
    def test_deterministic_reachable_seeds_under_all_banner_settings(
        self,
    ) -> None:
        catalog = fixture()
        for settings in (Settings(), Settings(False), Settings(True, 10)):
            for i in range(100):
                with self.subTest(settings=settings, seed=i):
                    result = generate(catalog, i, settings)
                    self.assertEqual(result, generate(catalog, i, settings))
                    _, unreachable, goal = playthrough(catalog, result["checks"], result["placements"])
                    self.assertEqual(unreachable, [])
                    self.assertTrue(goal)
                    self.assertEqual(
                        Counter(result["placements"].values()) & Counter(catalog["progression_pool"]),
                        Counter(catalog["progression_pool"]),
                    )

    def test_banner_pool_and_thresholds(self) -> None:
        self.assertNotIn(
            "excellent",
            [c["id"] for c in enabled_checks(fixture(), Settings(False))],
        )
        checks = enabled_checks(fixture(), Settings(True, 10))
        self.assertEqual(next(c for c in checks if c["id"] == "excellent")["threshold"], 20)
        catalog = fixture()
        catalog["checks"][-1]["threshold"] = 201
        self.assertEqual(enabled_checks(catalog, Settings(True, 10))[-1]["threshold"], 21)

    def test_missing_references_and_duplicate_checks_fail(self) -> None:
        catalog = fixture()
        catalog["checks"][0]["requires"] = {"item": "missing"}
        with self.assertRaises(ValueError):
            validate_catalog(catalog)
        catalog = fixture()
        catalog["checks"].append(copy.deepcopy(catalog["checks"][0]))
        with self.assertRaises(ValueError):
            validate_catalog(catalog)

    def test_self_locked_catalog_fails_instead_of_emitting_seed(self) -> None:
        catalog = fixture()
        for check in catalog["checks"]:
            check["requires"] = {"item": "hammer"}
        with self.assertRaises(ValueError):
            generate(catalog, 1)

    def test_star_reward_and_door_requirements_are_distinct(self) -> None:
        checks = {c["id"]: c for c in fixture()["checks"]}
        self.assertFalse(requirement_met(checks["stage_1_2"]["requires"], Counter({"clear_w1_1": 1})))
        self.assertTrue(requirement_met(checks["stage_1_2"]["requires"], Counter({"star_1_1_exit": 1})))
        full = Counter(paperization=1, door_place_1_2=1, door_sticker=1)
        self.assertTrue(requirement_met(checks["door"]["requires"], full))
        for item in full:
            partial = full.copy()
            partial[item] = 0
            self.assertFalse(requirement_met(checks["door"]["requires"], partial))


class RewardTests(unittest.TestCase):
    def test_generic_unlock_gives_copy_and_changes_shops_and_drops(
        self,
    ) -> None:
        state = RewardState()
        items = fixture()["items"]
        self.assertEqual(state.ordinary_sticker("secret_door"), "kamek_flip_flop")
        self.assertFalse(state.shop_sells("secret_door"))
        state.deliver("check", "door_sticker", items)
        self.assertEqual(state.sticker_inventory["secret_door"], 1)
        self.assertTrue(state.shop_sells("secret_door"))
        self.assertEqual(state.ordinary_sticker("secret_door"), "secret_door")

    def test_thing_unlock_and_check_persistence(self) -> None:
        state = RewardState()
        items = fixture()["items"]
        self.assertTrue(state.deliver("thing_pickup", "fan", items))
        self.assertTrue(state.shop_sells("fan", thing=True))
        self.assertFalse(state.shop_sells("fan"))
        restored = RewardState.from_save(state.to_save())
        self.assertFalse(restored.deliver("thing_pickup", "fan", items))
        self.assertEqual(restored.sticker_inventory["fan"], 1)
        self.assertNotIn("museum_fan", restored.completed_checks)

    def test_fillers_do_not_unlock_stickers_and_coins_are_once_only(
        self,
    ) -> None:
        state = RewardState()
        items = fixture()["items"]
        state.deliver("filler", "door_copy", items)
        self.assertFalse(state.shop_sells("secret_door"))
        self.assertEqual(state.sticker_inventory["kamek_flip_flop"], 1)
        state.deliver("enemy_goomba", "coins", items)
        state.deliver("enemy_goomba", "coins", items)
        self.assertEqual(state.coins, 20)


if __name__ == "__main__":
    unittest.main()
