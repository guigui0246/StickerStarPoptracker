import struct
import unittest
from dataclasses import replace

from ..integrations.citra.native import NativeGame
from ..integrations.rom.kdm import KdmDocument
from ..integrations.rom.mailbox import RemoteReward, RemoteSession, fit_mailbox, remote_function, saved_mailbox_bytes
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import decode_plan, encode_plan
from ..integrations.rom.switches import global_flags, register_saved_bytes
from . import test_native_bridge, test_native_delivery


class SavedMemory(test_native_bridge.FakeMemory):
    def __init__(self, profile):
        super().__init__(profile)
        self.saved = bytearray(256)

    def read(self, address, size):
        offset = address - self.pointer - 4
        if 0 <= offset < offset + size <= 256:
            return bytes(self.saved[offset:offset + size])
        return super().read(address, size)

    def write(self, address, data):
        offset = address - self.pointer - 4
        if 0 <= offset < offset + len(data) <= 256:
            self.writes.append((address, data))
            self.saved[offset:offset + len(data)] = data
            return
        super().write(address, data)

    def native_word(self, name, value):
        offset = (self.profile.word_index(name) - 3072) // 8
        self.saved[offset:offset + self.profile.word_size(name)] = value.to_bytes(self.profile.word_size(name), "little")


class SavedByteMailboxTests(unittest.TestCase):
    def test_saved_byte_allocation_preserves_native_tables_and_rejects_overflow(self):
        source = bytearray(test_native_delivery.small_switch_registry())
        field = KdmDocument(bytes(source)).tables["gsSwitchTable"].values[0].value[1]
        struct.pack_into("<i", source, field.offset, 219)
        patched, allocated = register_saved_bytes(bytes(source), saved_mailbox_bytes())
        self.assertEqual(len(allocated), 28)
        self.assertEqual([slot.index for slot in allocated], list(range(220, 248)))
        self.assertEqual(global_flags(KdmDocument(patched)), global_flags(KdmDocument(bytes(source))))
        with self.assertRaises(ValueError):
            register_saved_bytes(bytes(source), tuple(f"gs_rando_{i}" for i in range(37)))
        with self.assertRaises(ValueError):
            register_saved_bytes(patched, saved_mailbox_bytes())

    def test_large_local_placement_uses_saved_bytes_without_losing_receipts(self):
        coin = NativeReward(NativeRewardKind.COINS, 25)
        plan = DeliveryPlan(tuple(GoalBlockReward(f"room{i}", "GF_WM_A01_A02", coin) for i in range(425)),
                            remote_rewards=(RemoteReward(100, coin),), remote_session=RemoteSession("seed", 0, 1, "a" * 64))
        self.assertGreater(len(plan.flags), 1114)
        fitted = fit_mailbox(plan)
        self.assertTrue(fitted.saved_byte_mailbox)
        self.assertEqual(fitted.flags, fitted.local_flags)
        self.assertEqual(len(fitted.saved_bytes), 28)
        self.assertNotEqual(fitted.fingerprint, plan.fingerprint)
        self.assertEqual(decode_plan(encode_plan(fitted)), fitted)
        self.assertEqual(fitted.checks, plan.checks)

    def test_saved_byte_dispatch_commits_acknowledgement_after_native_grant(self):
        source = remote_function((RemoteReward(100, NativeReward(NativeRewardKind.COINS, 25)),), saved_bytes=True)
        self.assertIn("gs_rando_rpc_sequence_03 >= 128", source)
        self.assertNotIn("gf_rando_rpc_", source)
        self.assertLess(source.index("pouch_add_coin*(25)"), source.index("gs_rando_rpc_ack_ready_00 *= 0"))
        self.assertLess(source.index("gs_rando_rpc_ack_00 *= tempVar1"), source.index("gs_rando_rpc_ack_ready_00 *= 1"))

    def test_host_writes_only_request_bytes_and_ack_survives_snapshot(self):
        fixture = test_native_bridge.NativeBridgeTests()
        fixture.setUp()
        profile = replace(fixture.profile, flags={name: value for name, value in fixture.profile.flags.items() if not name.startswith("gf_rando_rpc_")},
                          saved_bytes={name: 220 + index for index, name in enumerate(saved_mailbox_bytes())})
        profile.validate_word_ownership()
        memory = SavedMemory(profile)
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {"star": 200})
        first = game.identity()
        self.assertEqual(game.identity(), first)
        self.assertEqual(len(memory.writes), 4)
        self.assertFalse(game.deliver("ap/0", test_native_bridge.ReceivedItem(100, 200, 2, 0)))
        self.assertFalse(game.received("ap/0"))
        memory.native_word("ack", 1)
        memory.native_word("ack_ready", 1)
        self.assertTrue(game.received("ap/0"))
        self.assertTrue(game.deliver("ap/0", test_native_bridge.ReceivedItem(100, 200, 2, 0)))
        ack_address = memory.base + profile.word_offset("ack")
        self.assertTrue(all(address + len(data) <= ack_address for address, data in memory.writes))
        with self.assertRaises(ValueError):
            game.write_host_word(memory.base, "ack", 5)

    def test_priority_page_receipt_never_acknowledges_an_earlier_sticker(self):
        fixture = test_native_bridge.NativeBridgeTests()
        fixture.setUp()
        flags = {name: value for name, value in fixture.profile.flags.items() if not name.startswith("gf_rando_rpc_")}
        flags.update({f"gf_rando_remote_page_{index}": 2200 + index for index in range(6)})
        page = NativeReward(NativeRewardKind.PAGE, 1)
        profile = replace(fixture.profile, flags=flags, saved_bytes={name: 220 + index for index, name in enumerate(saved_mailbox_bytes(True))},
                          selectors={100: 1, 101: 2}, selector_rewards={101: page}, priority_pages=True)
        profile.validate_word_ownership()
        memory = SavedMemory(profile)
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {"star": 200})
        from ..integrations.archipelago.runtime import ReceivedItem
        sticker, upgrade = ReceivedItem(100, 210, 2, 0), ReceivedItem(101, 211, 2, 1)
        game.prepare_pages(((0, sticker), (1, upgrade)))
        self.assertFalse(game.deliver("ap/0", sticker))
        self.assertFalse(game.deliver_priority("ap/1", upgrade))
        self.assertEqual(game.word(game.snapshot()[1], "ready"), 2)
        writes = len(memory.writes)
        game.deliver("ap/0", sticker)
        self.assertEqual(len(memory.writes), writes)
        memory.set_flag(flags["gf_rando_remote_page_0"], True)
        self.assertTrue(game.received("ap/1"))
        self.assertFalse(game.received("ap/0"))
        self.assertEqual(game.word(game.snapshot()[1], "ack"), 0)
        self.assertTrue(game.deliver_priority("ap/1", upgrade))
        memory.set_flag(flags["gf_rando_remote_page_0"], False)
        self.assertFalse(game.received("ap/1"))
        with self.assertRaises(ValueError):
            game.prepare_pages(((2, upgrade),))
        with self.assertRaises(ValueError):
            game.prepare_pages(tuple((index, upgrade) for index in range(7)))

    def test_page_plans_select_independent_receipts_and_no_prefix_ack_on_priority(self):
        from ..settings import AlbumPages
        coin, page = NativeReward(NativeRewardKind.COINS, 25), NativeReward(NativeRewardKind.PAGE, 1)
        plan = fit_mailbox(DeliveryPlan((GoalBlockReward("room", "GF_WM_A01_A02", coin),), album_pages=AlbumPages.RANDOMIZED,
                           remote_rewards=(RemoteReward(100, page),), remote_session=RemoteSession("seed", 0, 1, "a" * 64),
                           starting_rewards=(page,) * 6))
        self.assertTrue(plan.priority_pages)
        self.assertEqual(len(plan.saved_bytes), 29)
        self.assertEqual(len(plan.remote_page_flags), 6)
        self.assertEqual(decode_plan(encode_plan(plan)), plan)
        source = remote_function(plan.remote_rewards, saved_bytes=True, priority_pages=True)
        self.assertLess(source.index("gf_rando_remote_page_0 *= true"), source.index("if ( gs_rando_rpc_ready_00 == 2 )"))
        self.assertLess(source.index("if ( gs_rando_rpc_ready_00 == 2 )"), source.index("gs_rando_rpc_ack_ready_00 *= 0"))
        self.assertIn("gs_rando_rpc_page_rank_00 >= 6", source)

    def test_priority_capability_does_not_acknowledge_a_blocked_scrap_and_replays_after_rollback(self):
        fixture = test_native_bridge.NativeBridgeTests()
        fixture.setUp()
        flags = {name: value for name, value in fixture.profile.flags.items() if not name.startswith("gf_rando_rpc_")}
        flags.update({f"gf_rando_remote_page_{index}": 2200 + index for index in range(6)})
        flags["gf_rando_ability_paperization"] = 2210
        page = NativeReward(NativeRewardKind.PAGE, 1)
        ability = NativeReward(NativeRewardKind.ABILITY, "paperization")
        profile = replace(fixture.profile, flags=flags,
                          saved_bytes={name: 220 + index for index, name in enumerate(saved_mailbox_bytes(True))},
                          selectors={100: 1, 101: 2, 102: 3}, selector_rewards={101: page, 102: ability},
                          priority_pages=True, priority_capabilities=True)
        profile.validate_word_ownership()
        memory = SavedMemory(profile)
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {"star": 200})
        scrap = test_native_bridge.ReceivedItem(100, 210, 2, 0)
        unlock = test_native_bridge.ReceivedItem(102, 211, 2, 1)
        game.prepare_pages(((0, scrap), (1, unlock)))
        self.assertFalse(game.deliver("ap/0", scrap))
        self.assertTrue(game.is_priority_item(unlock))
        self.assertFalse(game.deliver_priority("ap/1", unlock))
        writes = len(memory.writes)
        game.deliver("ap/0", scrap)
        self.assertEqual(len(memory.writes), writes)
        memory.set_flag(flags["gf_rando_ability_paperization"], True)
        self.assertTrue(game.received("ap/1"))
        self.assertFalse(game.received("ap/0"))
        self.assertEqual(game.word(game.snapshot()[1], "ack"), 0)
        self.assertFalse(game.deliver("ap/0", scrap))
        memory.set_flag(flags["gf_rando_ability_paperization"], False)
        self.assertFalse(game.received("ap/1"))
        self.assertFalse(game.deliver_priority("ap/1", unlock))
        with self.assertRaises(ValueError):
            game.prepare_pages(((2, unlock),))

    def test_priority_runtime_accepts_only_inventory_free_idempotent_entitlements(self):
        rewards = (RemoteReward(100, NativeReward(NativeRewardKind.PAGE, 1)),
                   RemoteReward(101, NativeReward(NativeRewardKind.ABILITY, "paperization")),
                   RemoteReward(102, NativeReward(NativeRewardKind.COINS, 25)),
                   RemoteReward(103, NativeReward(NativeRewardKind.ITEM, "PK_HEI_5_BRIDGE")))
        source = remote_function(rewards, saved_bytes=True, priority_pages=True)
        self.assertIn("== 2 && ( tempVar2 == 1 || tempVar2 == 2 ) == false", source)
        self.assertLess(source.index("if ( gs_rando_rpc_ready_00 == 2 )"), source.index("gs_rando_rpc_ack_ready_00 *= 0"))

    def test_game_owned_pending_byte_cannot_share_a_host_mailbox_slot(self):
        fixture = test_native_bridge.NativeBridgeTests()
        fixture.setUp()
        profile = replace(fixture.profile,
                          flags={name: value for name, value in fixture.profile.flags.items() if not name.startswith("gf_rando_rpc_")},
                          saved_bytes={name: 220 + index for index, name in enumerate(saved_mailbox_bytes())},
                          game_saved_bytes={"gs_rando_peel_pending": 248})
        profile.validate_word_ownership()
        with self.assertRaisesRegex(ValueError, "Game-owned"):
            replace(profile, game_saved_bytes={"gs_rando_peel_pending": 220}).validate_word_ownership()
        memory = SavedMemory(profile)
        memory.saved[248] = 17
        game = NativeGame(memory, profile, "seed", 0, 1, "a" * 64, {"star": 200})
        game.identity()
        game.deliver("ap/0", test_native_bridge.ReceivedItem(100, 200, 2, 0))
        self.assertEqual(memory.saved[248], 17)
