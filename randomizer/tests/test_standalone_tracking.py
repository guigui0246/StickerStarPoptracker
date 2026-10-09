from typing import Any, cast
import unittest
from dataclasses import replace

from ..integrations.archipelago.standalone_tracking import StandaloneObservation
from ..integrations.citra.native import NativeGame
from ..integrations.rom.native_delivery import NativeReward, NativeRewardKind
from . import test_native_bridge


class StandaloneTrackingTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = test_native_bridge.NativeBridgeTests()
        fixture.setUp()
        self.profile = replace(
            fixture.profile,
            check_rewards={"star": NativeReward(NativeRewardKind.COINS, 25)},
            flags=fixture.profile.flags | {"gf_rando_starting_0000": 1582},
        )
        self.memory = test_native_bridge.FakeMemory(self.profile)
        self.game = NativeGame(self.memory, self.profile, "seed", 0, 1, "a" * 64, {"star": 200})
        self.config = {
            "format_version": 1,
            "seed": "seed",
            "catalog_hash": "a" * 64,
            "save_seed_fingerprint": self.profile.fingerprint.hex(),
            "locations": {"star": 200},
            "rewards": {"star": {"item": 100, "reward": {"kind": "coins", "value": 25}}},
            "starting": [{"item": 101, "reward": {"kind": "coins", "value": 10}}],
        }
        self.report = {"starting_rewards": [{"kind": "coins", "value": 10}]}

    def test_collection_and_delivery_are_distinct_and_tracking_never_writes(self) -> None:
        observer = StandaloneObservation(self.config, self.profile, self.game, cast(Any, self).report)
        self.memory.set_flag(1580, True)
        self.assertEqual(observer.snapshot().checks, (200,))
        self.assertEqual(observer.snapshot().items, ())
        self.memory.set_flag(1582, True)
        self.assertEqual(observer.snapshot().items[0].location, -2)
        self.memory.set_flag(1581, True)
        self.assertEqual([item.item for item in observer.snapshot().items], [101, 100])
        self.memory.set_flag(1581, False)
        self.assertEqual([item.item for item in observer.snapshot().items], [101])
        self.assertEqual(self.memory.writes, [])

    def test_wrong_identity_or_native_placement_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            StandaloneObservation(self.config | {"seed": "wrong"}, self.profile, self.game, cast(Any, self).report)
        with self.assertRaises(ValueError):
            StandaloneObservation(
                cast(Any, self.config | {"rewards": {"star": {"item": 100, "reward": {"kind": "coins", "value": 99}}}}),
                self.profile,
                self.game,
                cast(Any, self).report,
            )
