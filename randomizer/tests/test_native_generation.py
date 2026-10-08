from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..domain import EndGoal, GameDefinition, Item, Location, Rules, StartingRegion
from ..integrations.rom.native_delivery import BannerReward, FlagReward, GoalBlockReward, NativeReward, NativeRewardKind, PickupReward, ScriptReward
from ..integrations.rom.native_generation import NativeBindings, bind_seed, catalog_digest, generate_native_seed
from ..settings import AlbumPages, Banners, Settings
from ..standalone.generation import Seed


class NativeGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        hammer = Item("hammer", "Hammer")
        paper = Item("paper", "Paperization")
        coins = Item("coins", "Coins", False)
        victory = Item("victory", "Victory")
        self.game = GameDefinition((hammer, paper, coins, victory), (StartingRegion("menu", "Menu"),),
            (Location("first", "First", "menu"), Location("second", "Second", "menu", Rules.has("hammer")),
             Location("third", "Third", "menu"), EndGoal("end", "Win", "menu", Rules.all_of(Rules.has("hammer"), Rules.has("paper")), victory)),
            (), ("hammer", "paper", "coins"))
        dummy = NativeReward(NativeRewardKind.COINS, 1)
        self.bindings = NativeBindings(
            {"hammer": NativeReward(NativeRewardKind.ABILITY, "hammer"), "paper": NativeReward(NativeRewardKind.ABILITY, "paperization"),
             "coins": NativeReward(NativeRewardKind.COINS, 20), "victory": NativeReward(NativeRewardKind.VICTORY, 1)},
            {"first": PickupReward("hei_1_00", "thing", "REAL_FAN", dummy),
             "second": GoalBlockReward("hei_1_01", "GF_WM_A01_A02", dummy),
             "third": FlagReward("museum", "gf_museum_test", dummy),
             "end": ScriptReward("victory", "Script/Map/W6_BOS/w6_bos_04.bin", "koopa_battle_after_event_init", dummy)})

    def test_solved_seed_binds_exact_rewards_and_fixed_victory(self) -> None:
        for number in range(20):
            generated, plan = generate_native_seed(self.game, self.bindings, str(number))
            self.assertTrue(generated.won)
            self.assertEqual(plan.seed_name, str(number))
            self.assertEqual([check.reward for check in plan.checks[:3]], [self.bindings.items[generated.placements[loc.id]] for loc in self.game.locations[:3]])
            self.assertEqual(plan.checks[-1].reward.kind, NativeRewardKind.VICTORY)
            self.assertTrue(plan.ability_mode)
            self.assertEqual(generate_native_seed(self.game, self.bindings, str(number)), (generated, plan))

    def test_unreachable_placement_and_incomplete_or_duplicate_bindings_fail(self) -> None:
        bad = Seed("bad", {"first": "coins", "second": "hammer", "third": "paper"}, (), True)
        with self.assertRaises(ValueError):
            bind_seed(self.game, bad, self.bindings)
        for bindings in (replace(self.bindings, items={}), replace(self.bindings, locations={}),
                         replace(self.bindings, locations=self.bindings.locations | {"third": self.bindings.locations["first"]})):
            with self.assertRaises(ValueError):
                generate_native_seed(self.game, bindings, "test")
        with self.assertRaises(ValueError):
            generate_native_seed(replace(self.game, starting_items=("hammer",)), self.bindings, "test")

    def test_precollected_ability_is_bound_and_has_a_native_receipt(self) -> None:
        game = replace(self.game, pool=("coins", "paper", "coins"), starting_items=("hammer",))
        _, plan = generate_native_seed(game, self.bindings, "starting")
        self.assertEqual(plan.starting_rewards, (self.bindings.items["hammer"],))
        self.assertIn("gf_rando_starting_0000", plan.flags)
        self.assertIn("if ( gf_rando_starting_0000 == false )", plan.delivery_body())
        self.assertIn("gf_rando_ability_hammer *= true", plan.delivery_body())

    def test_page_settings_change_existing_rewards_without_extra_checks(self) -> None:
        page = Item("album_page", "Album page")
        extra = tuple(Location(f"extra{index}", f"Extra {index}", "menu") for index in range(5))
        game = replace(self.game, items=self.game.items + (page,), locations=self.game.locations + extra,
                       pool=("hammer", "paper") + ("coins",) * 6)
        dummy = NativeReward(NativeRewardKind.COINS, 1)
        bindings = replace(self.bindings, items=self.bindings.items | {page.id: NativeReward(NativeRewardKind.PAGE, 1)},
                           locations=self.bindings.locations | {location.id: FlagReward("event", f"gf_{location.id}", dummy) for location in extra})
        seed, plan = generate_native_seed(game, bindings, "pages", Settings(album_pages=AlbumPages.RANDOMIZED))
        self.assertEqual(sum(reward.kind == NativeRewardKind.PAGE for reward in plan.rewards), 6)
        self.assertEqual(len(plan.checks), len(game.locations))
        self.assertEqual(list(seed.placements.values()).count(page.id), 6)
        page_pool = replace(game, pool=("hammer", "paper") + (page.id,) * 6)
        _, plan = generate_native_seed(page_pool, bindings, "pages", Settings(album_pages=AlbumPages.ALL_AT_START))
        self.assertFalse(any(reward.kind == NativeRewardKind.PAGE for reward in plan.rewards))
        self.assertEqual(len(plan.checks), len(game.locations))

    def test_banner_settings_require_the_catalog_to_match_enabled_checks(self) -> None:
        banner = BannerReward("million_coin", Banners.ORIGINAL, NativeReward(NativeRewardKind.COINS, 1))
        bindings = replace(self.bindings, locations=self.bindings.locations | {"third": banner})
        _, plan = generate_native_seed(self.game, bindings, "test", Settings(banners=Banners.REDUCED))
        self.assertEqual(plan.checks[2].mode, Banners.REDUCED)
        generated, plan = generate_native_seed(self.game, bindings, "test", Settings(banners=Banners.OFF))
        self.assertNotIn("third", generated.placements)
        self.assertEqual(len(plan.checks), 3)
        self.assertFalse(any(isinstance(check, BannerReward) for check in plan.checks))
        no_filler = replace(self.game, pool=("hammer", "paper", "hammer"))
        with self.assertRaises(ValueError):
            generate_native_seed(no_filler, bindings, "test", Settings(banners=Banners.OFF))

    def test_loading_rejects_stale_catalog_hash_and_embedded_source_rewards(self) -> None:
        catalog = {"format_version": 2, "test": "graph"}
        data = {"format_version": 1, "catalog_sha256": catalog_digest(catalog), "items": {"coin": {"kind": "coins", "value": 20}},
                "locations": [{"location": "check", "source": {"category": "event", "source_flag": "gf_example"}}]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bindings.json"
            path.write_text(json.dumps(data))
            self.assertEqual(NativeBindings.load(path, catalog).items["coin"].value, 20)
            with self.assertRaises(ValueError):
                NativeBindings.load(path, {"format_version": 2, "test": "changed"})
            data["locations"][0]["source"]["reward"] = {"kind": "coins", "value": 999}
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                NativeBindings.load(path, catalog)
