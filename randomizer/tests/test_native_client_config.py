from copy import deepcopy
from dataclasses import replace
import unittest

from ..integrations.archipelago.client_config import NativeClientConfig
from ..integrations.rom.native_delivery import NativeReward, NativeRewardKind
from . import test_native_bridge


class NativeClientConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        bridge = test_native_bridge.NativeBridgeTests()
        bridge.setUp()
        coins = NativeReward(NativeRewardKind.COINS, 25)
        self.profile = replace(bridge.profile, check_rewards={"star": coins}, selector_rewards={100: coins})
        self.data = {"format_version": 1, "game": "Paper Mario: Sticker Star (Native Catalog)", "name": "Player",
                     "seed": "seed", "catalog_hash": "a" * 64, "save_seed_fingerprint": self.profile.fingerprint.hex(),
                     "locations": {"star": 9}, "local_rewards": [[100, 9, 1, 0]],
                     "settings": {"album_pages": "all_at_start", "banners": "original"}}

    def test_generated_configuration_matches_the_native_session_and_placements(self) -> None:
        config = NativeClientConfig.parse(self.data)
        config.validate(self.profile)
        self.assertEqual(config.locations, {"star": 9})
        self.assertEqual(config.local_rewards[0].item, 100)

    def test_wrong_seed_catalog_receipt_and_player_are_rejected_before_connection(self) -> None:
        for key, value in (("seed", "other"), ("catalog_hash", "b" * 64), ("save_seed_fingerprint", "0" * 32),
                           ("local_rewards", [[100, 9, 2, 0]]), ("local_rewards", [[101, 9, 1, 0]]),
                           ("locations", {"unknown": 9})):
            data = deepcopy(self.data)
            data[key] = value
            with self.assertRaises(ValueError):
                NativeClientConfig.parse(data).validate(self.profile)

    def test_invalid_types_duplicate_ids_and_duplicate_local_placements_fail(self) -> None:
        for key, value in (("format_version", True), ("locations", {"star": 9, "second": 9}),
                           ("local_rewards", [[100, 9, 1, 0], [100, 9, 1, 0]]), ("extra", 1)):
            data = deepcopy(self.data)
            data[key] = value
            with self.assertRaises(ValueError):
                NativeClientConfig.parse(data)
