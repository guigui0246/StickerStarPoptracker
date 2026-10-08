from collections import Counter
from dataclasses import replace
import unittest
from ..data.example import example_game
from ..domain import EndGoal, Path, Rules, StartingRegion, Vector
from ..standalone.generation import (
    InventoryState,
    generate_seed,
    playthrough,
    reachable_regions,
)


class GraphTests(unittest.TestCase):
    def test_menu_is_the_only_unconditionally_reachable_region(self) -> None:
        game = example_game()
        self.assertEqual(
            reachable_regions(game, InventoryState(Counter())), {"map", "field"}
        )
        self.assertNotIn(
            "town", reachable_regions(game, InventoryState(Counter(hammer=1)))
        )

    def test_directional_requirements(self) -> None:
        game = example_game()
        vector = game.paths[1].reverse
        self.assertFalse(vector.rules.allows(InventoryState(Counter())))
        self.assertTrue(vector.rules.allows(InventoryState(Counter(hammer=1))))
        with self.assertRaises(ValueError):
            Path("bad", Vector("map", "town"), Vector("field", "map"))

    def test_seed_collects_fixed_events_and_goals(self) -> None:
        game = example_game()
        for seed in range(100):
            result = generate_seed(game, seed)
            self.assertTrue(result.won)
            self.assertEqual(sum(map(len, result.spheres)), len(game.locations))
            self.assertFalse(set(result.placements) & game.fixed_rewards.keys())
            self.assertEqual(result, generate_seed(game, str(seed)))
        self.assertIn("rescue", {key for sphere in result.spheres for key in sphere})

    def test_end_goal_requires_its_region_and_rule(self) -> None:
        game = example_game()
        result = playthrough(
            game,
            {
                "map_gift": "coins",
                "field_pickup": "decalburg_access",
                "town_gift": "hammer",
            },
        )
        self.assertTrue(result.won)
        sphere_index = {
            key: index for index, sphere in enumerate(result.spheres) for key in sphere
        }
        self.assertLess(sphere_index["rescue"], sphere_index["boss"])
        self.assertLess(sphere_index["boss"], sphere_index["end"])

    def test_invalid_worlds_and_pools_fail(self) -> None:
        game = example_game()
        with self.assertRaises(ValueError):
            replace(
                game, regions=game.regions + (StartingRegion("other", "Other Menu"),)
            )
        with self.assertRaises(ValueError):
            replace(game, pool=("toad_rescued", "hammer", "coins"))
        with self.assertRaises(ValueError):
            replace(
                game,
                locations=tuple(
                    loc for loc in game.locations if not isinstance(loc, EndGoal)
                ),
            )
        with self.assertRaises(ValueError):
            playthrough(game, {})

    def test_counted_and_alternative_rules(self) -> None:
        rule = Rules.all_of(
            Rules.has("star", 2), Rules.any_of(Rules.has("hammer"), Rules.has("fan"))
        )
        self.assertFalse(rule.allows(InventoryState(Counter(star=1, hammer=1))))
        self.assertTrue(rule.allows(InventoryState(Counter(star=2, fan=1))))

    def test_unreachable_graph_cannot_generate(self) -> None:
        game = example_game()
        locations = tuple(
            replace(loc, rules=Rules.has("hammer"))
            if loc.id in {"map_gift", "field_pickup"}
            else loc
            for loc in game.locations
        )
        with self.assertRaises(ValueError):
            generate_seed(replace(game, locations=locations), 1, attempts=10)


if __name__ == "__main__":
    unittest.main()
