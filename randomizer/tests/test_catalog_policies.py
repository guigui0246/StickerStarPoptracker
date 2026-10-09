"""Verify settings change the filled graph and native delivery consistently."""

from dataclasses import replace
import unittest

from ..data.catalog import parse_catalog
from ..domain import EndGoal, GameDefinition, Item, Location, Rules, StartingRegion
from ..integrations.rom.native_delivery import EnemyReward, NativeReward, NativeRewardKind, ScriptReward
from ..integrations.rom.native_generation import NativeBindings, configure_catalog, generate_native_seed
from ..integrations.rom.royal_patch import FINAL_BOSS
from ..settings import AlbumPages, DoorStickers, EnemyRewards, GenericStickers, Museum, Settings
from .test_native_ap_catalog import fixture


class CatalogPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        catalog, raw = fixture()
        self.game = parse_catalog(catalog)
        self.bindings = NativeBindings.parse(raw, catalog)

    def test_museum_filter_retains_progression_and_end_goal(self) -> None:
        for mode, count in ((Museum.ALL, 6), (Museum.NORMAL, 6), (Museum.THINGS, 0), (Museum.OFF, 0)):
            with self.subTest(mode=mode):
                seed, plan = generate_native_seed(self.game, self.bindings, "museum", Settings(museum=mode))
                self.assertEqual(sum(check.id.startswith("museum/") for check in plan.checks), count)
                self.assertTrue(seed.won)
                self.assertEqual(sum(check.reward.kind == NativeRewardKind.VICTORY for check in plan.checks), 1)

    def test_enemy_filter_and_vanilla_pages_do_not_disable_the_goal(self) -> None:
        source = EnemyReward("KURI", "Script/Battle/Enemy/battle_kuri.bin", "dead",
                             NativeReward(NativeRewardKind.COINS, 25))
        bindings = replace(self.bindings, locations=self.bindings.locations | {"star0": source})
        seed, plan = generate_native_seed(
            self.game, bindings, "enemy", Settings(AlbumPages.VANILLA, enemy_rewards=EnemyRewards.OFF),
        )
        self.assertNotIn("star0", seed.placements)
        self.assertIsNone(plan.album_pages)
        self.assertTrue(seed.won)

    def test_vanilla_places_are_starting_entitlements_without_door_sticker_grants(self) -> None:
        bindings = replace(self.bindings, items=self.bindings.items | {
            "town": NativeReward(NativeRewardKind.DOOR_ACCESS, "door_1"),
        })
        seed, plan = generate_native_seed(self.game, bindings, "doors", Settings(door_stickers=DoorStickers.VANILLA))
        self.assertNotIn("town", seed.placements.values())
        self.assertEqual(plan.starting_rewards, (NativeReward(NativeRewardKind.DOOR_ACCESS, "door_1"),))

    def test_vanilla_generics_remove_unlock_rules_but_preserve_copy_starting_inventory(self) -> None:
        jump, copy = Item("jump", "Jump"), Item("copy", "Jump copy")
        coin, win = Item("coin", "Coin", False), Item("win", "Win")
        game = GameDefinition((jump, copy, coin, win), (StartingRegion("menu", "Menu"),), (
            Location("gift", "Gift", "menu", Rules.has("jump")),
            EndGoal("end", "End", "menu", Rules.has("jump"), win),
        ), (), ("jump",), ("jump",))
        bindings = NativeBindings({
            "jump": NativeReward(NativeRewardKind.STICKER_UNLOCK, "SL_JUMP"),
            "copy": NativeReward(NativeRewardKind.STICKER_COPY, "SL_JUMP"),
            "coin": NativeReward(NativeRewardKind.COINS, 25), "win": NativeReward(NativeRewardKind.VICTORY, 1),
        }, {
            "gift": self.bindings.locations["star0"],
            "end": ScriptReward("victory", FINAL_BOSS, "koopa_battle_after_event_init",
                                NativeReward(NativeRewardKind.VICTORY, 1)),
        })
        configured, _ = configure_catalog(game, bindings, Settings(generic_stickers=GenericStickers.DISABLED))
        self.assertEqual(configured.pool, ("coin",))
        self.assertEqual(configured.starting_items, ("copy",))
        self.assertFalse(configured.locations[0].rules.referenced_items())
