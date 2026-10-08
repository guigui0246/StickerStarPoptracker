"""Script-side single-writer mailbox for sequenced remote reward requests.

Each host-owned value occupies an entire aligned GF word. Native code never
writes request words; the host never writes acknowledgement words.
"""

from __future__ import annotations

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
        if self.reward.kind in {NativeRewardKind.VICTORY, NativeRewardKind.REMOTE, NativeRewardKind.EVENT}:
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
    bits = {"item": 16, "ready": 8, "ack_ready": 1}.get(name, 32)
    return tuple(f"gf_rando_rpc_{name}_{bit:02d}" for bit in range(bits))


def mailbox_flags(start_index: int) -> tuple[str, ...]:
    # GF setters write complete words. Put the game-owned acknowledgement
    # guard before alignment padding; only host-owned fields share the final
    # request word. No host write can overlap a game-owned flag word.
    guard = word_flags("ack_ready")
    padding = tuple(f"gf_rando_rpc_padding_{bit:02d}" for bit in range((-(start_index + len(guard))) % 32))
    words = ("save_a", "save_b", "save_c", "save_d", "sequence", "ack", "item", "ready")
    reserved = tuple(f"gf_rando_rpc_reserved_{bit:02d}" for bit in range(8))
    return guard + padding + tuple(flag for name in words for flag in word_flags(name)) + reserved


def decode_word(name: str, variable: str) -> list[str]:
    lines = [f"\t{variable} = 0;"]
    # Positive 31-bit values avoid signed integer overflow in the VM.
    for bit, flag in enumerate(word_flags(name)[:31]):
        lines.append(f"\tif ( {flag} ) {{\n\t\t{variable} = {variable} + {1 << bit};\n\t}}")
    return lines


def remote_function(rewards: tuple[RemoteReward, ...], shuffle_royals: bool = False, sticker_policy: StickerPolicy | None = None,
                    starting_item_ids: tuple[int, ...] = (), starting_flags: tuple[str, ...] = ()) -> str:
    lines = ["private rando_remote()  {", "\ttemp tempVar0;", "\ttemp tempVar1;", "\ttemp tempVar2;", "\ttemp tempVar3;"]
    lines.extend(["\tif ( gf_rando_rpc_ready_00 == false ) {\n\t\treturn*;\n\t}",
                  "\tif ( gf_rando_rpc_sequence_31 ) {\n\t\treturn*;\n\t}"])
    lines.extend(decode_word("sequence", "tempVar0"))
    lines.extend(decode_word("ack", "tempVar1"))
    lines.extend(["\tif ( tempVar0 <= tempVar1 || tempVar0 == 0 ) {\n\t\treturn*;\n\t}"])
    lines.extend(decode_word("item", "tempVar2"))
    lines.append("\ttempVar3 = false;")
    if starting_item_ids:
        if len(starting_item_ids) != len(starting_flags):
            raise ValueError("Precollected mailbox selectors require matching native receipts")
        selectors = {entry.item_id: index for index, entry in enumerate(rewards, 1)}
        lines.append(f"\tif ( tempVar0 <= {len(starting_item_ids)} ) {{")
        for index, (identifier, flag) in enumerate(zip(starting_item_ids, starting_flags, strict=True), 1):
            lines.extend([f"\t\tif ( tempVar0 == {index} && tempVar2 == {selectors[identifier]} && {flag} ) {{",
                          "\t\t\ttempVar3 = true;", "\t\t}"])
        lines.append("\t} else {")
    dispatch_start = len(lines)
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
            lines.append(f'\t\ttempVar3 = rando_item_grant*("{native_item}");')
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
    if starting_item_ids:
        lines[dispatch_start:] = ["\t" + line for line in lines[dispatch_start:]]
        lines.append("\t}")
    lines.extend(["\tif ( tempVar3 == false ) {\n\t\treturn*;\n\t}", "\tgf_rando_rpc_ack_ready_00 *= false;"])
    # Acknowledgement is published last, after the native grant has succeeded.
    for bit in range(30, -1, -1):
        value = 1 << bit
        lines.extend([f"\tif ( tempVar0 >= {value} ) {{", f"\t\tgf_rando_rpc_ack_{bit:02d} *= true;",
                      f"\t\ttempVar0 = tempVar0 - {value};", "\t} else {", f"\t\tgf_rando_rpc_ack_{bit:02d} *= false;", "\t}"])
    lines.extend(["\tgf_rando_rpc_ack_31 *= false;", "\tgf_rando_rpc_ack_ready_00 *= true;", "}"])
    return "\n".join(lines) + "\n"
