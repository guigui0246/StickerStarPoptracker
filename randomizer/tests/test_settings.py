import unittest

from ..settings import AlbumPages, Banners, DoorStickers, EnemyRewards, GenericStickers, Museum, Settings
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind


class SettingsTests(unittest.TestCase):
    def test_extended_modes_roundtrip_and_vanilla_page_policy(self) -> None:
        settings = Settings(AlbumPages.VANILLA, Banners.REDUCED, Museum.THINGS, EnemyRewards.OFF,
                            DoorStickers.VANILLA, GenericStickers.DISABLED)
        self.assertEqual(Settings.from_json(settings.to_json()), settings)
        with self.assertRaises(ValueError):
            Settings.from_json(settings.to_json() | {"generic_stickers": "plando"})

    def test_banner_threshold_rounding_and_disable(self) -> None:
        settings = Settings(banners=Banners.REDUCED)
        self.assertEqual([settings.banner_threshold(n) for n in (1, 9, 10, 11, 99, 100, 101)], [1, 1, 1, 2, 10, 10, 11])
        self.assertIsNone(Settings(banners=Banners.OFF).banner_threshold(10))
        for n in (0, -1, True):
            with self.assertRaises(ValueError):
                settings.banner_threshold(n)

    def test_strict_settings_roundtrip_and_unsafe_infinite(self) -> None:
        settings = Settings(AlbumPages.RANDOMIZED, Banners.OFF)
        self.assertEqual(Settings.from_json(settings.to_json()), settings)
        for raw in ({}, {"album_pages": "infinite", "banners": "off"}, {"album_pages": "randomized", "banners": True}):
            with self.assertRaises(ValueError):
                Settings.from_json(raw)

    def test_page_rewards_require_exact_pool_and_selected_mode(self) -> None:
        checks = tuple(GoalBlockReward(f"map_{i}", "GF_WM_A01_A02", NativeReward(NativeRewardKind.PAGE, 1)) for i in range(6))
        plan = DeliveryPlan(checks, AlbumPages.RANDOMIZED)
        self.assertEqual(plan.delivery_body().count("rando_page_grant*()"), 6)
        self.assertEqual(plan.page_function().count('item_try_addpouch*("SL_PAGE", true)'), 6)
        self.assertEqual(len(plan.page_flags), 6)
        for flag in plan.page_flags:
            self.assertIn(f"{flag} == false", plan.page_function())
            self.assertIn(f"{flag} *= true", plan.page_function())
        self.assertNotIn("pouch_get_max_seal_page", plan.delivery_body() + plan.page_function())
        for mode, pool in ((None, checks), (AlbumPages.ALL_AT_START, checks), (AlbumPages.RANDOMIZED, checks[:5])):
            with self.assertRaises(ValueError):
                DeliveryPlan(pool, mode)

    def test_starting_pages_are_once_and_settings_are_seed_bound(self) -> None:
        check = GoalBlockReward("map", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 10))
        plan = DeliveryPlan((check,), AlbumPages.ALL_AT_START)
        self.assertEqual(plan.delivery_body().count('item_try_addpouch*("SL_PAGE", true)'), 6)
        self.assertIn("gf_rando_album_initialized == false", plan.delivery_body())
        self.assertNotEqual(plan.fingerprint, DeliveryPlan((check,)).fingerprint)
