import struct
import unittest

from ..integrations.rom.kdm import KdmDocument
from ..integrations.rom.mailbox import RemoteReward, remote_function
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.pickups import record, text
from ..integrations.rom.stickers import StickerPolicy, patch_shops


def shop_fixture() -> bytes:
    names = ("SL_JUMP", "SL_FAN", "SHOP_TOWN", "SHOP_IWA", "SHOP_DOR", "SHOP_SNOW", "SHOP_KAZAN", "SHOP_KOOPA", "SHOP_MONO")
    strings = bytearray(struct.pack("<I", len(names)))
    addresses = {}
    for name in names:
        addresses[name] = 40 + len(strings)
        raw = name.encode() + b"\0"
        strings.extend(raw + bytes((-len(raw)) % 4))
    sections = [40, 40 + len(strings)]
    sections.extend((sections[1] + 4, sections[1] + 8, sections[1] + 12))
    definition = struct.pack("<IHH7I", 1, 21, 5, 0, 0, 3, 3, 8, 3, 13)
    sections.append(sections[4] + len(definition))
    data = bytearray(struct.pack("<I", 2))
    record_addresses = []
    for index, item in enumerate(("SL_JUMP", "SL_FAN")):
        record_addresses.append(sections[5] + len(data) + 8)
        data.extend(struct.pack("<4HIIH2xII", 22 + index, 5, 21, 5, addresses[item], 0, 0, 0, 0))
    sections.append(sections[5] + len(data))
    tables = bytearray(struct.pack("<I7I", 7, *(addresses[name] for name in names[2:])))
    for index, name in enumerate(names[2:]):
        tables.extend(struct.pack("<4HII", 24 + index, 2, 15, 2, record_addresses[int(name == "SHOP_MONO")], 0))
    sections.append(sections[6] + len(tables))
    return b"KDMR\x00\x01\x01\x00" + struct.pack("<8I", *(offset // 4 for offset in sections)) + strings + bytes(12) + definition + data + tables + bytes(4)


class StickerTests(unittest.TestCase):
    policy = StickerPolicy(("SL_JUMP", "SL_HAMMER", "SL_W6_SANDAL_S"), (("SL_FAN", "REAL_FAN"),))

    def test_all_generic_shops_share_unlock_stock_and_thing_shop_is_preserved(self) -> None:
        source = KdmDocument(shop_fixture())
        result = KdmDocument(patch_shops(source.data, self.policy))
        for name, table in result.tables.items():
            contents = [tuple(text(field) for field in record(result.pointed_array(pointer.value).values[0], 5)[:2]) for pointer in table.values[:-1]]
            if name == "SHOP_MONO":
                self.assertEqual(contents, [("SL_FAN", "")])
            else:
                self.assertEqual(contents, [(item, self.policy.flag(item)) for item in self.policy.generic])
            self.assertEqual(table.values[-1].value.address, 0)

    def test_copies_convert_without_unlocking_and_successful_unlocks_bypass_conversion(self) -> None:
        copy = "\n".join(self.policy.grant("SL_JUMP", unlock=False, result="result"))
        unlock = "\n".join(self.policy.grant("SL_JUMP", unlock=True, result="result"))
        self.assertIn('"SL_W6_SANDAL_S"', copy)
        self.assertNotIn("*= true", copy)
        self.assertNotIn("SL_W6_SANDAL_S", unlock)
        self.assertIn("gf_rando_unlock_sl_jump *= true", unlock)
        self.assertLess(unlock.index("*= true"), unlock.index("rando_item_grant"))
        thing_copy = "\n".join(self.policy.grant("SL_FAN", unlock=False, result="result"))
        thing_unlock = "\n".join(self.policy.grant("SL_FAN", unlock=True, result="result"))
        self.assertNotIn("pouch_already_get_real_item_debug", thing_copy)
        self.assertIn('pouch_already_get_real_item_debug*("REAL_FAN")', thing_unlock)

    def test_remote_and_local_rewards_use_same_copy_policy_and_bind_seed(self) -> None:
        reward = NativeReward(NativeRewardKind.STICKER_COPY, "SL_JUMP")
        check = GoalBlockReward("map", "GF_WM_A01_A02", reward)
        plan = DeliveryPlan((check,), sticker_policy=self.policy)
        self.assertIn('"SL_W6_SANDAL_S"', plan.delivery_body())
        self.assertIn('"SL_W6_SANDAL_S"', remote_function((RemoteReward(100, reward),), sticker_policy=self.policy))
        self.assertNotEqual(plan.fingerprint, DeliveryPlan((check,)).fingerprint)
        with self.assertRaises(ValueError):
            DeliveryPlan((check,)).delivery_body()
        with self.assertRaises(ValueError):
            self.policy.grant("SL_UNKNOWN", unlock=True, result="result")

    def test_policy_rejects_injected_or_mismatched_ids(self) -> None:
        for generic, things in ((("SL_W6_SANDAL_S", 'SL_JUMP";'), ()), (("SL_W6_SANDAL_S",), (("SL_FAN", "REAL_BED"),))):
            with self.assertRaises(ValueError):
                StickerPolicy(generic, things)


if __name__ == "__main__":
    unittest.main()
