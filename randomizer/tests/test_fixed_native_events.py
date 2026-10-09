from dataclasses import replace
import unittest

from ..data.catalog import parse_catalog
from ..integrations.rom.mailbox import RemoteReward
from ..integrations.rom.native_delivery import DeliveryPlan, FlagReward, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.native_generation import NativeBindings
from ..integrations.rom.plan_io import decode_plan, encode_plan
from . import test_native_ap_catalog


class FixedNativeEventTests(unittest.TestCase):
    def test_story_events_observe_original_flags_without_inventory_or_extra_save_bits(self) -> None:
        normal = GoalBlockReward("room", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 25))
        event = FlagReward(
            "event", "gf_native_bridge_repaired", NativeReward(NativeRewardKind.EVENT, "gf_native_bridge_repaired")
        )
        base, plan = DeliveryPlan((normal,)), DeliveryPlan((normal, event))
        self.assertEqual(len(base.flags), len(plan.flags))
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        self.assertIn("gf_native_bridge_repaired", plan.required_references)
        self.assertNotIn("gf_native_bridge_repaired *=", plan.delivery_body())
        self.assertNotIn("gf_rando_delivered_0001", plan.delivery_body())

    def test_events_cannot_be_precollected_or_received_from_another_world(self) -> None:
        event = NativeReward(NativeRewardKind.EVENT, "gf_native_bridge_repaired")
        with self.assertRaises(ValueError):
            RemoteReward(123, event)
        source = FlagReward("event", "gf_native_bridge_repaired", event)
        with self.assertRaises(ValueError):
            DeliveryPlan((source,), starting_rewards=(event,))
        with self.assertRaises(ValueError):
            DeliveryPlan((replace(source, source_flag="gf_other_story"),))

    def test_catalog_binding_rejects_an_event_in_the_randomized_pool(self) -> None:
        raw, bound = test_native_ap_catalog.fixture()
        game = parse_catalog(raw)
        bindings = NativeBindings.parse(bound, raw)
        items = bindings.items | {"coins": NativeReward(NativeRewardKind.EVENT, "gf_native_story")}
        with self.assertRaisesRegex(ValueError, "cannot be shuffled"):
            replace(bindings, items=items).validate(game)
