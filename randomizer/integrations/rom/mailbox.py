"""Script-side single-writer mailbox for sequenced remote reward requests.

The GF layout isolates host-owned words; the compact GS layout uses native
byte stores. Native code never writes requests, and the host never writes
acknowledgements.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import TYPE_CHECKING
from .native_delivery import capability_receipt, DeliveryPlan, NativeReward, NativeRewardKind
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


def byte_fields(name: str) -> tuple[str, ...]:
    size = {"item": 2, "ready": 1, "ack_ready": 1, "page_rank": 1}.get(name, 4)
    return tuple(f"gs_rando_rpc_{name}_{index:02d}" for index in range(size))


def saved_mailbox_bytes(priority_pages: bool = False) -> tuple[str, ...]:
    return tuple(field for name in ("save_a", "save_b", "save_c", "save_d", "sequence", "item", "ready", "ack", "ack_ready")
                 for field in byte_fields(name)) + (byte_fields("page_rank") if priority_pages else ())


def fit_mailbox(plan: DeliveryPlan) -> DeliveryPlan:
    """Use the GS mailbox when the conventional GF layout would overflow."""
    if any(entry.reward.kind == NativeRewardKind.PAGE for entry in plan.remote_rewards):
        plan = replace(plan, saved_byte_mailbox=True, priority_pages=True)
    if plan.remote_rewards and not plan.saved_byte_mailbox and len(plan.flags) > 1114:
        plan = replace(plan, saved_byte_mailbox=True)
    if len(plan.flags) > 1114:
        raise ValueError(f"Native placement needs {len(plan.flags)} saved flags; this revision supports 1114")
    return plan


def mailbox_flags(start_index: int) -> tuple[str, ...]:
    # GF setters write complete words. Put the game-owned acknowledgement
    # guard before alignment padding; only host-owned fields share the final
    # request word. No host write can overlap a game-owned flag word.
    guard = word_flags("ack_ready")
    padding = tuple(f"gf_rando_rpc_padding_{bit:02d}" for bit in range((-(start_index + len(guard))) % 32))
    words = ("save_a", "save_b", "save_c", "save_d", "sequence", "ack", "item", "ready")
    reserved = tuple(f"gf_rando_rpc_reserved_{bit:02d}" for bit in range(8))
    return guard + padding + tuple(flag for name in words for flag in word_flags(name)) + reserved


def decode_word(name: str, variable: str, saved_bytes: bool = False) -> list[str]:
    if saved_bytes:
        return [f"\t{variable} = " + " + ".join(f"{field} * {256 ** index}" for index, field in enumerate(byte_fields(name))) + ";"]
    lines = [f"\t{variable} = 0;"]
    # Positive 31-bit values avoid signed integer overflow in the VM.
    for bit, flag in enumerate(word_flags(name)[:31]):
        lines.append(f"\tif ( {flag} ) {{\n\t\t{variable} = {variable} + {1 << bit};\n\t}}")
    return lines


def remote_function(rewards: tuple[RemoteReward, ...], shuffle_royals: bool = False, sticker_policy: StickerPolicy | None = None,
                    starting_item_ids: tuple[int, ...] = (), starting_flags: tuple[str, ...] = (), saved_bytes: bool = False, priority_pages: bool = False) -> str:
    if priority_pages and (not saved_bytes or not any(entry.reward.kind == NativeRewardKind.PAGE for entry in rewards)):
        raise ValueError("Priority commands require a saved-byte page mailbox")
    lines = ["private rando_remote()  {", "\ttemp tempVar0;", "\ttemp tempVar1;", "\ttemp tempVar2;", "\ttemp tempVar3;"]
    ready = byte_fields("ready")[0] if saved_bytes else "gf_rando_rpc_ready_00"
    guard = byte_fields("ack_ready")[0] if saved_bytes else "gf_rando_rpc_ack_ready_00"
    invalid = "gs_rando_rpc_sequence_03 >= 128" if saved_bytes else "gf_rando_rpc_sequence_31"
    empty = "0" if saved_bytes else "false"
    lines.extend([f"\tif ( {ready} == {empty} ) {{\n\t\treturn*;\n\t}}",
                  f"\tif ( {invalid} ) {{\n\t\treturn*;\n\t}}"])
    lines.extend(decode_word("sequence", "tempVar0", saved_bytes))
    lines.extend(decode_word("ack", "tempVar1", saved_bytes))
    lines.extend(["\tif ( tempVar0 <= tempVar1 || tempVar0 == 0 ) {\n\t\treturn*;\n\t}"])
    lines.extend(decode_word("item", "tempVar2", saved_bytes))
    if priority_pages:
        page_selectors = " || ".join(f"tempVar2 == {index}" for index, entry in enumerate(rewards, 1) if entry.reward.kind == NativeRewardKind.PAGE)
        priority_selectors = " || ".join(f"tempVar2 == {index}" for index, entry in enumerate(rewards, 1) if entry.reward.kind == NativeRewardKind.PAGE or capability_receipt(entry.reward, shuffle_royals))
        lines.extend(["\tif ( gs_rando_rpc_ready_00 != 1 && gs_rando_rpc_ready_00 != 2 ) {\n\t\treturn*;\n\t}",
                      f"\tif ( gs_rando_rpc_ready_00 == 2 && ( {priority_selectors} ) == false ) {{\n\t\treturn*;\n\t}}",
                      f"\tif ( ( {page_selectors} ) && gs_rando_rpc_page_rank_00 >= 6 ) {{\n\t\treturn*;\n\t}}"])

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
            lines.append("\t\ttempVar3 = rando_remote_page*();" if priority_pages else "\t\ttempVar3 = rando_page_grant*();")
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
    if priority_pages:
        lines.append("\tif ( tempVar3 ) {")
        for index in range(6):
            lines.append(f"\t\tif ( ( {page_selectors} ) && gs_rando_rpc_page_rank_00 == {index} ) {{\n\t\t\tgf_rando_remote_page_{index} *= true;\n\t\t}}")
        lines.extend(["\t}", "\tif ( gs_rando_rpc_ready_00 == 2 ) {\n\t\treturn*;\n\t}"])
    lines.extend(["\tif ( tempVar3 == false ) {\n\t\treturn*;\n\t}", f"\t{guard} *= {empty};"])
    if saved_bytes:
        for index in range(3, -1, -1):
            factor = 256 ** index
            lines.extend([f"\ttempVar1 = tempVar0 / {factor};", f"\tgs_rando_rpc_ack_{index:02d} *= tempVar1;",
                          f"\ttempVar0 = tempVar0 - tempVar1 * {factor};"])
        lines.extend([f"\t{guard} *= 1;", "}"])
        return "\n".join(lines) + "\n"
    # Acknowledgement is published last, after the native grant has succeeded.
    for bit in range(30, -1, -1):
        value = 1 << bit
        lines.extend([f"\tif ( tempVar0 >= {value} ) {{", f"\t\tgf_rando_rpc_ack_{bit:02d} *= true;",
                      f"\t\ttempVar0 = tempVar0 - {value};", "\t} else {", f"\t\tgf_rando_rpc_ack_{bit:02d} *= false;", "\t}"])
    lines.extend(["\tgf_rando_rpc_ack_31 *= false;", "\tgf_rando_rpc_ack_ready_00 *= true;", "}"])
    return "\n".join(lines) + "\n"
