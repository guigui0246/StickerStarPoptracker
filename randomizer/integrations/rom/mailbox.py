"""Script-side single-writer mailbox for sequenced remote reward requests.

Each host-owned value occupies an entire aligned GF word. Native code never
writes request words; the host never writes acknowledgement words.
"""

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING
from .native_delivery import DeliveryPlan, NativeReward, NativeRewardKind
if TYPE_CHECKING:
    from .stickers import StickerPolicy


@dataclass(frozen=True)
class RemoteReward:
    item_id: int
    reward: NativeReward

    def __post_init__(self) -> None:
        if type(self.item_id) is not int or self.item_id < 1:
            raise ValueError("Remote rewards require positive stable item IDs")
        if self.reward.kind in {NativeRewardKind.VICTORY, NativeRewardKind.REMOTE}:
            raise ValueError("Incoming items cannot grant victory or remote ownership")


@dataclass(frozen=True)
class RemoteSession:
    seed: str
    team: int
    slot: int
    catalog_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.seed, str) or not self.seed or type(self.team) is not int or self.team < 0 or type(self.slot) is not int or self.slot < 1:
            raise ValueError("Invalid remote seed or player identity")
        if not isinstance(self.catalog_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.catalog_hash):
            raise ValueError("Expected a catalog SHA-256 identity")


def word_flags(name: str) -> tuple[str, ...]:
    return tuple(f"gf_rando_rpc_{name}_{bit:02d}" for bit in range(32))


def mailbox_flags(start_index: int) -> tuple[str, ...]:
    padding = tuple(f"gf_rando_rpc_padding_{bit:02d}" for bit in range((-start_index) % 32))
    words = ("item", "sequence", "ready", "ack", "ack_ready", "save_a", "save_b", "save_c", "save_d")
    return padding + tuple(flag for name in words for flag in word_flags(name))


def decode_word(name: str, variable: str) -> list[str]:
    lines = [f"\t{variable} = 0;"]
    # Positive 31-bit values avoid signed integer overflow in the VM.
    for bit, flag in enumerate(word_flags(name)[:31]):
        lines.append(f"\tif ( {flag} ) {{\n\t\t{variable} = {variable} + {1 << bit};\n\t}}")
    return lines


def remote_function(rewards: tuple[RemoteReward, ...], shuffle_royals: bool = False, sticker_policy: StickerPolicy | None = None) -> str:
    lines = ["private rando_remote()  {", "\ttemp tempVar0;", "\ttemp tempVar1;", "\ttemp tempVar2;", "\ttemp tempVar3;"]
    lines.extend(["\tif ( gf_rando_rpc_ready_00 == false ) {\n\t\treturn*;\n\t}",
                  "\tif ( gf_rando_rpc_sequence_31 || gf_rando_rpc_item_31 ) {\n\t\treturn*;\n\t}"])
    lines.extend(decode_word("sequence", "tempVar0"))
    lines.extend(decode_word("ack", "tempVar1"))
    lines.extend(["\tif ( tempVar0 <= tempVar1 || tempVar0 == 0 ) {\n\t\treturn*;\n\t}"])
    lines.extend(decode_word("item", "tempVar2"))
    lines.append("\ttempVar3 = false;")
    for selector, entry in enumerate(rewards, 1):
        reward = entry.reward
        lines.append(f"\tif ( tempVar2 == {selector} ) {{")
        if reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}:
            if sticker_policy is None:
                raise ValueError("Sticker selectors require a ROM-derived policy")
            lines.extend("\t\t" + line.replace("\n", "\n\t\t") for line in sticker_policy.grant(str(reward.value), unlock=reward.kind == NativeRewardKind.STICKER_UNLOCK, result="tempVar3"))
        elif reward.kind == NativeRewardKind.PAGE:
            lines.append("\t\ttempVar3 = rando_page_grant*();")
        elif reward.kind == NativeRewardKind.ITEM:
            native_item = reward.value
            lines.append(f'\t\ttempVar3 = item_try_addpouch*("{native_item}", false);')
        else:
            if reward.kind == NativeRewardKind.COINS:
                lines.append(f"\t\tpouch_add_coin*({reward.value});")
            elif reward.kind == NativeRewardKind.ABILITY:
                lines.extend("\t\t" + line for line in DeliveryPlan.ability_grant(str(reward.value)))
            elif reward.kind == NativeRewardKind.STAGE_ACCESS:
                lines.append(f"\t\tgf_rando_stage_{str(reward.value).lower()} *= true;")
            elif reward.kind == NativeRewardKind.DOOR_ACCESS:
                lines.append(f"\t\tgf_rando_door_{str(reward.value).lower()} *= true;")
            elif reward.kind == NativeRewardKind.BOSS_ACCESS:
                lines.append(f"\t\tgf_rando_boss_{reward.value} *= true;")
            elif reward.kind == NativeRewardKind.ROYAL:
                lines.append(f"\t\tpouch_set_royal_seal*(pouch_royal_w{reward.value});")
                if shuffle_royals:
                    lines.append(f"\t\tgf_rando_royal_{reward.value} *= true;")
            elif reward.kind == NativeRewardKind.MINI_STAR:
                lines.extend([f'\t\tmobj_set_gf*("{reward.value}");', f'\t\twm_set_gf*("{reward.value}");'])
            lines.append("\t\ttempVar3 = true;")
        lines.append("\t}")
    lines.extend(["\tif ( tempVar3 == false ) {\n\t\treturn*;\n\t}", "\tgf_rando_rpc_ack_ready_00 *= false;"])
    # Acknowledgement is published last, after the native grant has succeeded.
    for bit in range(30, -1, -1):
        value = 1 << bit
        lines.extend([f"\tif ( tempVar0 >= {value} ) {{", f"\t\tgf_rando_rpc_ack_{bit:02d} *= true;",
                      f"\t\ttempVar0 = tempVar0 - {value};", "\t} else {", f"\t\tgf_rando_rpc_ack_{bit:02d} *= false;", "\t}"])
    lines.extend(["\tgf_rando_rpc_ack_31 *= false;", "\tgf_rando_rpc_ack_ready_00 *= true;", "}"])
    return "\n".join(lines) + "\n"
