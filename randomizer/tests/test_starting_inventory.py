from dataclasses import replace
import unittest

from ..integrations.rom.native_delivery import DeliveryPlan, FlagReward, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import decode_plan, encode_plan
from ..integrations.rom.stickers import StickerPolicy
from ..integrations.rom.mailbox import RemoteReward, RemoteSession
from ..integrations.rom.shared_runtime import runtime_functions


class StartingInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = DeliveryPlan((FlagReward("event", "gf_test", NativeReward(NativeRewardKind.COINS, 10)),))

    def test_starting_inventory_roundtrip_fingerprint_and_independent_receipts(self) -> None:
        rewards = (NativeReward(NativeRewardKind.COINS, 25),) * 2
        plan = replace(self.plan, starting_rewards=rewards)
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        self.assertEqual(decode_plan(encode_plan(self.plan)), self.plan)
        self.assertNotEqual(plan.fingerprint, self.plan.fingerprint)
        self.assertEqual(len(plan.flags), len(self.plan.flags) + 2)
        self.assertEqual(plan.delivery_body().count("pouch_add_coin*(25)"), 2)
        for receipt in plan.starting_flags:
            self.assertIn(f"if ( {receipt} == false )", plan.delivery_body())
            self.assertIn(f"{receipt} *= true", plan.delivery_body())

    def test_full_inventory_retries_without_marking_starting_copy_delivered(self) -> None:
        policy = StickerPolicy(("SL_JUMP", "SL_W6_SANDAL_S"), ())
        plan = replace(
            self.plan, starting_rewards=(NativeReward(NativeRewardKind.STICKER_UNLOCK, "SL_JUMP"),), sticker_policy=policy
        )
        body = plan.delivery_body()
        self.assertLess(body.index("gf_rando_unlock_sl_jump *= true"), body.index('rando_item_grant*("SL_JUMP")'))
        self.assertIn("if ( tempVar0 ) {\n\t\t\tgf_rando_starting_0000 *= true", body)
        self.assertIn("gf_rando_unlock_sl_jump", plan.required_references)

    def test_starting_capabilities_participate_in_native_gate_registry(self) -> None:
        plan = replace(
            self.plan,
            starting_rewards=(
                NativeReward(NativeRewardKind.STAGE_ACCESS, "A01"),
                NativeReward(NativeRewardKind.DOOR_ACCESS, "A02"),
                NativeReward(NativeRewardKind.BOSS_ACCESS, "harbor"),
            ),
        )
        self.assertEqual(plan.stage_access_codes, ("A01",))
        self.assertEqual(plan.door_access_codes, ("A02",))
        self.assertEqual(plan.boss_access_codes, ("harbor",))

    def test_network_and_victory_cannot_be_precollected(self) -> None:
        for kind in (NativeRewardKind.REMOTE, NativeRewardKind.VICTORY):
            with self.assertRaises(ValueError):
                replace(self.plan, starting_rewards=(NativeReward(kind, 1),))

    def test_ap_starting_echo_uses_the_saved_receipt_instead_of_granting_twice(self) -> None:
        reward = NativeReward(NativeRewardKind.COINS, 25)
        plan = replace(
            self.plan,
            starting_rewards=(reward,),
            starting_item_ids=(100,),
            remote_rewards=(RemoteReward(100, reward),),
            remote_session=RemoteSession("seed", 0, 1, "a" * 64),
        )
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        remote = runtime_functions(plan).split("private rando_remote()", 1)[1]
        self.assertIn("if ( tempVar0 <= 1 )", remote)
        self.assertIn("tempVar0 == 1 && tempVar2 == 1 && gf_rando_starting_0000", remote)
        branch, normal = remote.split("\t} else {", 1)
        self.assertNotIn("pouch_add_coin", branch)
        self.assertIn("pouch_add_coin*(25)", normal)
        self.assertNotEqual(plan.fingerprint, replace(plan, starting_item_ids=()).fingerprint)
        for identifiers in ((101,), (100, 100)):
            with self.assertRaises(ValueError):
                replace(plan, starting_item_ids=identifiers)
