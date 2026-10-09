"""Exercise the no-logic catalog and exact native binding together."""

from collections import Counter
import unittest

from ..data.no_logic import build_no_logic_catalog
from ..integrations.rom.native_delivery import FlagReward, NativeReward, NativeRewardKind, ScriptReward
from ..integrations.rom.native_generation import generate_native_seed
from ..integrations.rom.production_sources import ProductionSources
from ..integrations.rom.royal_patch import FINAL_BOSS
from ..settings import AlbumPages, Settings


class NoLogicTests(unittest.TestCase):
    def sources(self) -> ProductionSources:
        coin = NativeReward(NativeRewardKind.COINS, 25)
        victory = NativeReward(NativeRewardKind.VICTORY, 1)
        rewards = (
            coin, victory, NativeReward(NativeRewardKind.ABILITY, "hammer"),
            NativeReward(NativeRewardKind.ABILITY, "paperization"),
            NativeReward(NativeRewardKind.STAGE_ACCESS, "X00"),
            NativeReward(NativeRewardKind.STAGE_ACCESS, "A01"),
            NativeReward(NativeRewardKind.STICKER_UNLOCK, "SL_JUMP"),
            NativeReward(NativeRewardKind.STICKER_COPY, "SL_JUMP"),
            NativeReward(NativeRewardKind.PAGE, 1),
        ) + tuple(NativeReward(NativeRewardKind.ROYAL, index) for index in range(1, 7))
        checks = tuple(FlagReward("museum", f"gf_test_{index}", coin) for index in range(12)) + (
            ScriptReward("boss", FINAL_BOSS, "get_royal_seal_event", coin),
        ) + tuple(
            FlagReward("boss", f"gf_evt_{world}_{level}_royal_seal", coin)
            for world, level in ((1, 6), (2, 5), (3, 12), (4, 5), (5, 6))
        ) + (
            ScriptReward("victory", FINAL_BOSS, "koopa_battle_after_event_init", victory),
        )
        return ProductionSources(checks, rewards, frozenset(), {})

    def test_all_observed_checks_bind_and_victory_is_fixed(self) -> None:
        _, game, bindings = build_no_logic_catalog(self.sources())
        seed, plan = generate_native_seed(game, bindings, "test")
        self.assertEqual(set(bindings.locations), {check.id for check in self.sources().checks})
        self.assertEqual(len(seed.placements), 18)
        self.assertEqual(len(seed.spheres), 1)
        self.assertEqual(len(game.fixed_rewards), 1)
        self.assertNotIn("victory/1", seed.placements.values())
        self.assertIn("stage_access/X00", game.starting_items)
        self.assertNotIn("sticker_unlock/SL_JUMP", game.starting_items)
        self.assertIn("sticker_copy/SL_JUMP", game.starting_items)
        self.assertIn("sticker_unlock/SL_JUMP", game.pool)
        self.assertIn(NativeReward(NativeRewardKind.STICKER_COPY, "SL_JUMP"), plan.starting_rewards)
        self.assertTrue(plan.shuffle_royals)
        self.assertFalse(plan.remote_rewards)
        self.assertEqual(seed, generate_native_seed(game, bindings, "test")[0])

    def test_randomized_pages_are_six_distinct_deliveries(self) -> None:
        _, game, bindings = build_no_logic_catalog(self.sources())
        seed, plan = generate_native_seed(game, bindings, "pages", Settings(AlbumPages.RANDOMIZED))
        self.assertEqual(Counter(seed.placements.values())["page/1"], 6)
        self.assertEqual(sum(check.reward.kind == NativeRewardKind.PAGE for check in plan.checks), 6)

    def test_missing_victory_and_overfull_progression_are_rejected(self) -> None:
        sources = self.sources()
        with self.assertRaisesRegex(ValueError, "Bowser victory"):
            build_no_logic_catalog(ProductionSources(sources.checks[:-1], sources.rewards, frozenset(), {}))
        extra = tuple(NativeReward(NativeRewardKind.ITEM, f"PK_TEST_{index}") for index in range(20))
        with self.assertRaisesRegex(ValueError, "cannot hold"):
            build_no_logic_catalog(ProductionSources(sources.checks, sources.rewards + extra, frozenset(), {}))
