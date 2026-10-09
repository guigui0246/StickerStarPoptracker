"""Persistent local reward delivery through the game's script VM.

This backend supports observed goal-block checks. It uses named global save
flags, retries inventory deliveries, and separates source checks from rewards.
It does not assert that a caller-supplied placement table is a solvable catalog.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import re
from typing import TYPE_CHECKING
from ...settings import AlbumPages
from ...settings import Banners

if TYPE_CHECKING:
    from .mailbox import RemoteReward, RemoteSession
    from .stickers import StickerPolicy


class NativeRewardKind(str, Enum):
    ITEM = "item"
    STICKER_UNLOCK = "sticker_unlock"
    STICKER_COPY = "sticker_copy"
    ABILITY = "ability"
    STAGE_ACCESS = "stage_access"
    DOOR_ACCESS = "door_access"
    BOSS_ACCESS = "boss_access"
    COINS = "coins"
    MINI_STAR = "mini_star"
    ROYAL = "royal"
    PAGE = "page"
    VICTORY = "victory"
    REMOTE = "remote"
    EVENT = "event"


@dataclass(frozen=True)
class NativeReward:
    kind: NativeRewardKind
    value: str | int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NativeRewardKind):
            raise ValueError("Reward kind must be a NativeRewardKind")
        if self.kind in {NativeRewardKind.ITEM, NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}:
            if not isinstance(self.value, str) or not re.fullmatch(r"(?:SL|IC|PK|REAL)_[A-Z0-9_]+", self.value):
                raise ValueError("Expected a native game item ID")
            if self.value == "SL_PAGE":
                raise ValueError("Page rewards require suppressing vanilla page grants; not yet supported by this hook")
            if self.kind != NativeRewardKind.ITEM and not self.value.startswith("SL_"):
                raise ValueError("Sticker unlocks and copies require a sticker ID")
        elif self.kind == NativeRewardKind.ABILITY:
            if self.value not in ("hammer", "paperization"):
                raise ValueError("Expected Hammer or Paperization")
        elif self.kind == NativeRewardKind.STAGE_ACCESS:
            if not isinstance(self.value, str) or not re.fullmatch(r"[A-FX][0-9]{2}", self.value):
                raise ValueError("Expected a native world-map stage code")
        elif self.kind == NativeRewardKind.DOOR_ACCESS:
            if not isinstance(self.value, str) or not re.fullmatch(r"(?:[A-F][0-9]{2}|[a-z][a-z0-9_]{0,95})", self.value):
                raise ValueError("Expected an exact native Secret Door identity or numbered stage")
        elif self.kind == NativeRewardKind.BOSS_ACCESS:
            if self.value not in ("w1", "w2", "w3", "w4", "w5", "w6", "harbor"):
                raise ValueError("Expected one of the six Royal bosses or Harbor boss")
        elif self.kind == NativeRewardKind.COINS:
            if type(self.value) is not int or not 1 <= self.value <= 9999:
                raise ValueError("Coin rewards must be between 1 and 9999")
        elif self.kind == NativeRewardKind.MINI_STAR:
            if not isinstance(self.value, str) or not re.fullmatch(r"GF_WM_[A-F][0-9]{2}_[A-F][0-9]{2}", self.value):
                raise ValueError("Expected a mini-star route flag")
        elif self.kind == NativeRewardKind.ROYAL:
            if type(self.value) is not int or not 1 <= self.value <= 6:
                raise ValueError("Royal Sticker index must be between 1 and 6")
        elif self.kind in {NativeRewardKind.PAGE, NativeRewardKind.VICTORY}:
            if type(self.value) is not int or self.value != 1:
                raise ValueError("Page and victory rewards have value one")
        elif self.kind == NativeRewardKind.REMOTE:
            if type(self.value) is not int or self.value < 1:
                raise ValueError("Remote ownership requires a positive player slot")
        elif self.kind == NativeRewardKind.EVENT:
            if not isinstance(self.value, str) or not re.fullmatch(r"gf_[a-z0-9_]+", self.value):
                raise ValueError("Fixed native events require an exact global story flag")
        else:
            raise ValueError("Unsupported native reward kind")


def capability_receipt(reward: NativeReward, shuffle_royals: bool = False) -> str | None:
    """Only idempotent entitlements can bypass a blocked inventory command."""
    prefixes = {
        NativeRewardKind.ABILITY: "ability",
        NativeRewardKind.STAGE_ACCESS: "stage",
        NativeRewardKind.DOOR_ACCESS: "door",
        NativeRewardKind.BOSS_ACCESS: "boss",
    }
    prefix = prefixes.get(reward.kind)
    if prefix is not None:
        return f"gf_rando_{prefix}_{str(reward.value).lower()}"
    if reward.kind == NativeRewardKind.ROYAL and shuffle_royals:
        return f"gf_rando_royal_{reward.value}"
    return None


@dataclass(frozen=True)
class GoalBlockReward:
    map_name: str
    source_flag: str
    reward: NativeReward

    def __post_init__(self) -> None:
        if not isinstance(self.map_name, str) or not re.fullmatch(r"[a-z0-9_]+", self.map_name):
            raise ValueError("Invalid native map ID")
        NativeReward(NativeRewardKind.MINI_STAR, self.source_flag)

    @property
    def id(self) -> str:
        return f"mini_star/{self.map_name}/{self.source_flag.lower()}"


@dataclass(frozen=True)
class PickupReward:
    map_name: str
    object_name: str
    source_item: str
    reward: NativeReward

    def __post_init__(self) -> None:
        if not isinstance(self.map_name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", self.map_name):
            raise ValueError("Invalid pickup map")
        if not isinstance(self.object_name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", self.object_name):
            raise ValueError("Invalid pickup object")
        if not isinstance(self.source_item, str) or not re.fullmatch(r"(?:REAL|PK)_[A-Z0-9_]+", self.source_item):
            raise ValueError("Only observed Thing and scrap pickup hooks are supported")

    @property
    def id(self) -> str:
        return f"pickup/{self.map_name}/{self.object_name}"


@dataclass(frozen=True)
class ContainerReward:
    map_name: str
    object_name: str
    source_item: str
    reward: NativeReward
    container_type: str = "TREASURE_FILE"

    def __post_init__(self) -> None:
        PickupReward(self.map_name, self.object_name, self.source_item, self.reward)
        if self.container_type != "TREASURE_FILE":
            raise ValueError("Only the observed deterministic treasure-file callback is supported")

    @property
    def id(self) -> str:
        return f"container/{self.map_name}/{self.object_name}"


@dataclass(frozen=True)
class PeelVariant:
    lock_id: str
    source_item: str

    def __post_init__(self) -> None:
        if not isinstance(self.lock_id, str) or not re.fullmatch(r"[a-z0-9_]+", self.lock_id):
            raise ValueError("Invalid native peel lock identity")
        if not isinstance(self.source_item, str) or not re.fullmatch(r"PK_(?!FIELD_)[A-Z0-9_]+", self.source_item):
            raise ValueError("Peel sources require a native inventory scrap")


@dataclass(frozen=True)
class PeelReward:
    map_name: str
    lock_id: str
    source_item: str
    reward: NativeReward
    variants: tuple[PeelVariant, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.map_name, str) or not re.fullmatch(r"[a-z0-9_]+", self.map_name):
            raise ValueError("Invalid peel map identity")
        PeelVariant(self.lock_id, self.source_item)
        if any(not isinstance(variant, PeelVariant) for variant in self.variants):
            raise ValueError("Peel aliases require typed native variants")
        if len(self.variants) > 16 or len({variant.lock_id for variant in self.hooks}) != len(self.hooks):
            raise ValueError("Peel aliases must be distinct and bounded")

    @property
    def hooks(self) -> tuple[PeelVariant, ...]:
        return (PeelVariant(self.lock_id, self.source_item),) + self.variants

    @property
    def id(self) -> str:
        return f"peel/{self.map_name}/{self.lock_id}"


@dataclass(frozen=True)
class FlagReward:
    category: str
    source_flag: str
    reward: NativeReward

    def __post_init__(self) -> None:
        if self.category not in {"museum", "kamek", "boss", "shop", "event"}:
            raise ValueError("Unsupported persistent event category")
        if not isinstance(self.source_flag, str) or not re.fullmatch(r"gf_[a-z0-9_]+", self.source_flag):
            raise ValueError("Expected a native global flag")

    @property
    def id(self) -> str:
        return f"{self.category}/{self.source_flag}"


HONORS = frozenset(
    {
        "parts_of_comet",
        "paper_door",
        "seal_collector",
        "max_heart",
        "million_coin",
        "btl_slot_machine",
        "btl_excellent",
        "btl_perfect",
    }
)


@dataclass(frozen=True)
class BannerReward:
    honor: str
    mode: Banners
    reward: NativeReward

    def __post_init__(self) -> None:
        if self.honor not in HONORS or self.mode not in {Banners.ORIGINAL, Banners.REDUCED}:
            raise ValueError("Expected an enabled native success banner")

    @property
    def id(self) -> str:
        return f"banner/{self.honor}"


@dataclass(frozen=True)
class ScriptReward:
    category: str
    script_file: str
    function: str
    reward: NativeReward

    def __post_init__(self) -> None:
        if self.category not in {"boss", "kamek", "shop", "event", "victory"}:
            raise ValueError("Unsupported script-event category")
        if not isinstance(self.script_file, str) or not re.fullmatch(
            r"Script/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.bin", self.script_file
        ):
            raise ValueError("Expected a native script path")
        if not isinstance(self.function, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.function):
            raise ValueError("Expected a native script function name")

    @property
    def id(self) -> str:
        return f"{self.category}/{self.script_file}/{self.function}"


@dataclass(frozen=True)
class EnemyVariant:
    unit_id: str
    script_file: str
    function: str


@dataclass(frozen=True)
class EnemyReward:
    unit_id: str
    script_file: str
    function: str
    reward: NativeReward
    type_id: str | None = None
    variants: tuple[EnemyVariant, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.unit_id, str)
            or not self.unit_id
            or len(self.unit_id) > 256
            or any(character in self.unit_id for character in '\\"\r\n\0')
        ):
            raise ValueError("Invalid native enemy unit identity")
        if not isinstance(self.script_file, str) or not re.fullmatch(
            r"Script/Battle/Enemy/[A-Za-z0-9_]+\.bin", self.script_file
        ):
            raise ValueError("Enemy checks require an observed battle script")
        if not isinstance(self.function, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.function):
            raise ValueError("Enemy checks require a native death callback")
        if self.type_id is not None and (
            not isinstance(self.type_id, str) or not re.fullmatch(r"enemy_name_[A-Za-z0-9_]+", self.type_id)
        ):
            raise ValueError("Enemy groups require an exact native type label")
        if self.variants and self.type_id is None:
            raise ValueError("Variant aliases require one shared enemy type identity")
        if any(not isinstance(variant, EnemyVariant) for variant in self.variants):
            raise ValueError("Enemy variants require typed native hook identities")
        if (
            len(self.variants) > 127
            or len({variant.unit_id for variant in self.variants} | {self.unit_id}) != len(self.variants) + 1
        ):
            raise ValueError("Enemy variants must be unique and bounded")
        for variant in self.variants:
            EnemyReward(variant.unit_id, variant.script_file, variant.function, self.reward)

    @property
    def hooks(self) -> tuple[EnemyVariant, ...]:
        return (EnemyVariant(self.unit_id, self.script_file, self.function),) + self.variants

    @property
    def id(self) -> str:
        if self.type_id is not None:
            return f"enemy/type/{self.type_id}"
        return "enemy/" + hashlib.sha256(self.unit_id.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class DeliveryPlan:
    checks: tuple[
        GoalBlockReward | PickupReward | ContainerReward | PeelReward | FlagReward | BannerReward | ScriptReward | EnemyReward,
        ...,
    ]
    album_pages: AlbumPages | None = None
    shuffle_royals: bool = False
    remote_rewards: tuple[RemoteReward, ...] = ()
    remote_session: RemoteSession | None = None
    sticker_policy: StickerPolicy | None = None
    skip_opening: bool = True
    skip_dialogue: bool = True
    seed_name: str | None = None
    starting_rewards: tuple[NativeReward, ...] = ()
    starting_item_ids: tuple[int, ...] = ()
    catalog_hash: str | None = None
    saved_byte_mailbox: bool = False
    priority_pages: bool = False

    def __post_init__(self) -> None:
        if type(self.priority_pages) is not bool or (
            self.priority_pages
            and (
                not self.saved_byte_mailbox
                or not any(entry.reward.kind == NativeRewardKind.PAGE for entry in self.remote_rewards)
            )
        ):
            raise ValueError("Priority pages require a saved-byte page mailbox")
        if type(self.saved_byte_mailbox) is not bool or (self.saved_byte_mailbox and not self.remote_rewards):
            raise ValueError("Saved-byte mailbox requires incoming rewards")
        if self.catalog_hash is not None and (
            not isinstance(self.catalog_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", self.catalog_hash)
        ):
            raise ValueError("Native catalogs require a SHA-256 identity")
        if (
            self.catalog_hash is not None
            and self.remote_session is not None
            and self.catalog_hash != self.remote_session.catalog_hash
        ):
            raise ValueError("Native catalog and network session disagree")
        if type(self.skip_opening) is not bool or type(self.skip_dialogue) is not bool:
            raise ValueError("Presentation skip settings must be boolean")
        if self.seed_name is not None and (
            not isinstance(self.seed_name, str) or not self.seed_name or len(self.seed_name) > 1024
        ):
            raise ValueError("Expected a bounded seed identity")
        if self.seed_name is not None and self.remote_session is not None and self.seed_name != self.remote_session.seed:
            raise ValueError("Native seed and remote session disagree")
        if not self.checks or len({check.id for check in self.checks}) != len(self.checks):
            raise ValueError("Delivery plans require unique native check IDs")
        if len(self.checks) > 1024:
            raise ValueError("Delivery plan exceeds the bounded native check limit")
        peels = [
            (check.map_name, hook.lock_id) for check in self.checks if isinstance(check, PeelReward) for hook in check.hooks
        ]
        if len(peels) != len(set(peels)):
            raise ValueError("A peel source cannot belong to multiple checks")
        units = [hook.unit_id for check in self.checks if isinstance(check, EnemyReward) for hook in check.hooks]
        if len(units) != len(set(units)):
            raise ValueError("An enemy unit cannot belong to two global victory checks")
        if len(self.starting_rewards) > 256 or any(
            not isinstance(reward, NativeReward)
            or reward.kind in {NativeRewardKind.REMOTE, NativeRewardKind.VICTORY, NativeRewardKind.EVENT}
            for reward in self.starting_rewards
        ):
            raise ValueError("Starting inventory requires bounded local non-victory rewards")
        if any(
            check.reward.kind == NativeRewardKind.EVENT
            and (not isinstance(check, FlagReward) or check.source_flag != check.reward.value)
            for check in self.checks
        ):
            raise ValueError("Fixed native events must observe their own original story flag")
        pages = sum(
            reward.kind == NativeRewardKind.PAGE
            for reward in tuple(check.reward for check in self.checks) + self.starting_rewards
        )
        if self.album_pages == AlbumPages.INFINITE:
            raise ValueError("Infinite inventory is not supported by native delivery")
        if self.album_pages is not None and not isinstance(self.album_pages, AlbumPages):
            raise ValueError("Invalid album-page mode")
        expected_pages = 6 if self.album_pages == AlbumPages.RANDOMIZED else 0
        remote_pages = any(entry.reward.kind == NativeRewardKind.PAGE for entry in self.remote_rewards)
        if remote_pages and self.album_pages != AlbumPages.RANDOMIZED:
            raise ValueError("Remote page rewards require randomized album pages")
        if pages != expected_pages and not (self.album_pages == AlbumPages.RANDOMIZED and remote_pages and pages <= 6):
            raise ValueError("Randomized albums require exactly six independent page rewards")
        if type(self.shuffle_royals) is not bool:
            raise ValueError("Royal shuffle setting must be boolean")
        if (
            len({entry.item_id for entry in self.remote_rewards}) != len(self.remote_rewards)
            or len(self.remote_rewards) > 4096
        ):
            raise ValueError("Remote item selectors must be unique and bounded")
        if bool(self.remote_rewards) != (self.remote_session is not None):
            raise ValueError("Remote mailbox requires a bound seed, player and catalog")
        if self.starting_item_ids:
            selectors = {entry.item_id: entry.reward for entry in self.remote_rewards}
            if len(self.starting_item_ids) != len(self.starting_rewards) or any(
                type(identifier) is not int or selectors.get(identifier) != reward
                for identifier, reward in zip(self.starting_item_ids, self.starting_rewards, strict=False)
            ):
                raise ValueError("AP starting item IDs must match each precollected native reward in server order")
        abilities = [
            reward.value
            for reward in tuple(check.reward for check in self.checks) + self.starting_rewards
            if reward.kind == NativeRewardKind.ABILITY
        ]
        capabilities = set(abilities) | {
            entry.reward.value for entry in self.remote_rewards if entry.reward.kind == NativeRewardKind.ABILITY
        }
        if capabilities and (capabilities != {"hammer", "paperization"} or len(abilities) != len(set(abilities))):
            raise ValueError("Ability shuffle requires both unique ability capabilities")
        if self.shuffle_royals:
            royals = sorted(
                int(reward.value)
                for reward in tuple(check.reward for check in self.checks) + self.starting_rewards
                if reward.kind == NativeRewardKind.ROYAL
            )
            required = {
                "gf_evt_1_6_royal_seal",
                "gf_evt_2_5_royal_seal",
                "gf_evt_3_12_royal_seal",
                "gf_evt_4_5_royal_seal",
                "gf_evt_5_6_royal_seal",
            }
            sources = {
                check.source_flag for check in self.checks if isinstance(check, FlagReward) and check.category == "boss"
            }
            final = any(
                isinstance(check, ScriptReward)
                and check.category == "boss"
                and check.script_file == "Script/Map/W6_BOS/w6_bos_04.bin"
                and check.function == "get_royal_seal_event"
                for check in self.checks
            )
            remote_royals = {
                int(entry.reward.value) for entry in self.remote_rewards if entry.reward.kind == NativeRewardKind.ROYAL
            }
            valid_pool = (
                royals == list(range(1, 7))
                if not self.remote_rewards
                else len(royals) == len(set(royals)) and set(royals) | remote_royals == set(range(1, 7))
            )
            if not valid_pool or not required <= sources or not final:
                raise ValueError("Royal shuffle requires all six Royal rewards and all six source boss checks")
        victories = [check for check in self.checks if check.reward.kind == NativeRewardKind.VICTORY]
        if len(victories) > 1 or any(
            not isinstance(check, ScriptReward)
            or check.category != "victory"
            or check.script_file != "Script/Map/W6_BOS/w6_bos_04.bin"
            or check.function != "koopa_battle_after_event_init"
            for check in victories
        ):
            raise ValueError("Victory must be fixed at Bowser's actual post-victory callback")

    @property
    def local_flags(self) -> tuple[str, ...]:
        initialization = ("gf_rando_album_initialized",) if self.album_pages is not None else ()
        royal_flags = tuple(f"gf_rando_royal_{index}" for index in range(1, 7)) if self.shuffle_royals else ()
        victory = ("gf_rando_victory",) if any(check.reward.kind == NativeRewardKind.VICTORY for check in self.checks) else ()
        unlocks = self.sticker_policy.flags if self.sticker_policy else ()
        receipts = tuple(
            flag
            for index, check in enumerate(self.checks)
            for flag in (
                (() if isinstance(check, FlagReward) else self.receipt_flags(index)[:1])
                if check.reward.kind in {NativeRewardKind.REMOTE, NativeRewardKind.EVENT}
                else (self.receipt_flags(index)[1:] if isinstance(check, FlagReward) else self.receipt_flags(index))
            )
        )
        return (
            self.seed_flags
            + initialization
            + self.page_flags
            + royal_flags
            + victory
            + self.ability_flags
            + self.stage_access_flags
            + self.door_access_flags
            + self.boss_access_flags
            + self.boss_pending_flags
            + unlocks
            + receipts
            + self.starting_flags
        )

    @property
    def starting_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_starting_{index:04d}" for index in range(len(self.starting_rewards)))

    @property
    def rewards(self) -> tuple[NativeReward, ...]:
        return (
            tuple(check.reward for check in self.checks)
            + tuple(entry.reward for entry in self.remote_rewards)
            + self.starting_rewards
        )

    @property
    def boss_access_codes(self) -> tuple[str, ...]:
        rewards = self.rewards
        return tuple(sorted({str(reward.value) for reward in rewards if reward.kind == NativeRewardKind.BOSS_ACCESS}))

    @property
    def boss_access_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_boss_{code}" for code in self.boss_access_codes)

    @property
    def boss_pending_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_boss_pending_{code}" for code in self.boss_access_codes if code != "harbor")

    @property
    def page_flags(self) -> tuple[str, ...]:
        return (
            tuple(f"gf_rando_page_received_{index}" for index in range(6)) if self.album_pages == AlbumPages.RANDOMIZED else ()
        )

    @staticmethod
    def page_grant(result: str) -> tuple[str, ...]:
        lines = [f"{result} = false;"]
        for index in range(6):
            lines.extend(
                [
                    f"if ( gf_rando_page_received_{index} == false ) {{",
                    f'\t{result} = item_try_addpouch*("SL_PAGE", true);',
                    f"\tif ( {result} ) {{\n\t\tgf_rando_page_received_{index} *= true;\n\t}}",
                    f"\treturn* {result};",
                    "}",
                ]
            )
        return tuple(lines)

    def page_function(self) -> str:
        return (
            "private rando_page_grant()  {\n\ttemp tempVar0;\n"
            + "\n".join("\t" + line.replace("\n", "\n\t") for line in self.page_grant("tempVar0"))
            + "\n\treturn* tempVar0;\n}\n"
        )

    @property
    def stage_access_codes(self) -> tuple[str, ...]:
        rewards = self.rewards
        return tuple(sorted({str(reward.value) for reward in rewards if reward.kind == NativeRewardKind.STAGE_ACCESS}))

    @property
    def stage_access_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_stage_{code.lower()}" for code in self.stage_access_codes)

    @property
    def door_access_codes(self) -> tuple[str, ...]:
        rewards = self.rewards
        return tuple(sorted({str(reward.value) for reward in rewards if reward.kind == NativeRewardKind.DOOR_ACCESS}))

    @property
    def door_access_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_door_{code.lower()}" for code in self.door_access_codes)

    @property
    def ability_mode(self) -> bool:
        return any(reward.kind == NativeRewardKind.ABILITY for reward in self.rewards)

    @property
    def ability_flags(self) -> tuple[str, ...]:
        return (
            ("gf_rando_abilities_initialized", "gf_rando_ability_hammer", "gf_rando_ability_paperization")
            if self.ability_mode
            else ()
        )

    @staticmethod
    def ability_grant(value: str) -> tuple[str, ...]:
        accessory, button = (
            ("pouch_hammer", "player_hammer_button") if value == "hammer" else ("pouch_lucie", "player_pepalyze_button")
        )
        return (
            f"gf_rando_ability_{value} *= true;",
            f"pouch_attach_accessory*({accessory});",
            f'player_set_ignore_key*("mario", {button}, false);',
        )

    @property
    def enemy_pending_flags(self) -> tuple[str, ...]:
        return tuple(self.enemy_pending(index) for index, check in enumerate(self.checks) if isinstance(check, EnemyReward))

    @staticmethod
    def enemy_pending(index: int) -> str:
        return f"rando_enemy_pending_{index:04d}"

    @property
    def flags(self) -> tuple[str, ...]:
        from .mailbox import mailbox_flags

        return (
            self.local_flags
            + self.remote_page_flags
            + (mailbox_flags(1446 + len(self.local_flags)) if self.remote_rewards and not self.saved_byte_mailbox else ())
        )

    @property
    def saved_bytes(self) -> tuple[str, ...]:
        from .mailbox import saved_mailbox_bytes

        mailbox = saved_mailbox_bytes(self.priority_pages) if self.saved_byte_mailbox else ()
        return mailbox + (("gs_rando_peel_pending",) if any(isinstance(check, PeelReward) for check in self.checks) else ())

    @property
    def remote_page_flags(self) -> tuple[str, ...]:
        return tuple(f"gf_rando_remote_page_{index}" for index in range(6)) if self.priority_pages else ()

    @property
    def references(self) -> tuple[str, ...]:
        return (
            self.flags
            + self.saved_bytes
            + tuple(sorted({check.source_flag for check in self.checks if isinstance(check, FlagReward)}))
        )

    @property
    def required_references(self) -> tuple[str, ...]:
        # Host-only nonce and reserved mailbox bits need registry storage, but
        # no VM references. The compiler correctly drops their declarations.
        rewards = self.rewards
        unlocks = {
            self.sticker_policy.flag(str(reward.value))
            for reward in rewards
            if self.sticker_policy
            and reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}
            and reward.value in self.sticker_policy.generic
        }
        return tuple(
            flag
            for flag in self.references
            if not flag.startswith(("gf_rando_enemy_pending_", "gf_rando_boss_pending_", "gs_rando_rpc_save_"))
            and (not flag.startswith("gf_rando_unlock_") or flag in unlocks)
            and (
                not flag.startswith("gf_rando_rpc_")
                or re.fullmatch(r"gf_rando_rpc_(?:item|sequence|ack)_[0-9]{2}", flag)
                or flag in {"gf_rando_rpc_ready_00", "gf_rando_rpc_ack_ready_00"}
            )
        )

    def receipt(self, index: int) -> tuple[str, str]:
        checked, delivered = self.receipt_flags(index)
        check = self.checks[index]
        return (check.source_flag if isinstance(check, FlagReward) else checked, delivered)

    @property
    def seed_flags(self) -> tuple[str, ...]:
        return ("gf_rando_seed_initialized",) + tuple(f"gf_rando_seed_{index:02d}" for index in range(128))

    @property
    def fingerprint(self) -> bytes:
        payload = []
        for check in self.checks:
            row = asdict(check)
            if isinstance(check, EnemyReward) and check.type_id is None:
                row.pop("type_id")
                row.pop("variants")
            payload.append(row)
        identity: list[object] = [
            payload,
            self.album_pages,
            self.shuffle_royals,
            [asdict(entry) for entry in self.remote_rewards],
            asdict(self.remote_session) if self.remote_session else None,
            asdict(self.sticker_policy) if self.sticker_policy else None,
            self.skip_opening,
            self.skip_dialogue,
            self.seed_name,
        ]
        if any(check.reward.kind == NativeRewardKind.REMOTE for check in self.checks):
            # Receipt compaction moves later flag indices. Never interpret an
            # earlier two-bit-layout save as this layout, even for the same seed.
            identity.append("compact-network-check-receipts-v1")
        if self.remote_rewards:
            identity.append(
                "native-saved-byte-mailbox-v1" if self.saved_byte_mailbox else "word-owner-safe-compact-mailbox-v2"
            )
        if self.priority_pages:
            identity.append("independent-remote-page-receipts-v1")
            if any(capability_receipt(entry.reward, self.shuffle_royals) for entry in self.remote_rewards):
                identity.append("priority-idempotent-capabilities-v1")
        if any(isinstance(check, PeelReward) for check in self.checks):
            identity.append("reserved-persistent-peel-returns-v2")
        if self.enemy_pending_flags:
            identity.append("transient-native-encounter-state-v1")
        if self.starting_rewards:
            identity.append(["native-starting-inventory-v1", [asdict(reward) for reward in self.starting_rewards]])
        if self.starting_item_ids:
            identity.append(["ap-precollected-native-receipts-v1", self.starting_item_ids])
        if self.sticker_policy is not None or any(
            reward.kind in {NativeRewardKind.ITEM, NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}
            for reward in self.rewards
        ):
            # Earlier scripts acknowledged successful fit checks without adding
            # the copy. Those receipts cannot safely be reused by this runtime.
            identity.append("native-inventory-fit-and-commit-v1")
        if self.shuffle_royals:
            identity.append("first-five-royals-castle-gate-v1")
        if self.catalog_hash is not None:
            identity.append(["native-catalog-binding-v1", self.catalog_hash])
        return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).digest()[:16]

    def seed_function(self) -> str:
        expected = tuple(bool(self.fingerprint[index // 8] & (1 << (index % 8))) for index in range(128))
        lines = ["private rando_seed_valid()  {", "\tif ( gf_rando_seed_initialized == false ) {"]
        lines.extend(
            f"\t\t{flag} *= {'true' if bit else 'false'};" for flag, bit in zip(self.seed_flags[1:], expected, strict=True)
        )
        lines.extend(["\t\tgf_rando_seed_initialized *= true;", "\t}"])
        lines.extend(
            f"\tif ( {flag} != {'true' if bit else 'false'} ) {{\n\t\treturn* false;\n\t}}"
            for flag, bit in zip(self.seed_flags[1:], expected, strict=True)
        )
        lines.extend(["\treturn* true;", "}"])
        return "\n".join(lines) + "\n"

    @staticmethod
    def receipt_flags(index: int) -> tuple[str, str]:
        return f"gf_rando_check_{index:04d}", f"gf_rando_delivered_{index:04d}"

    def grant_body(self, reward: NativeReward, delivered: str) -> list[str]:
        lines: list[str] = []
        if reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}:
            if self.sticker_policy is None:
                raise ValueError("Sticker rewards require a ROM-derived policy")
            lines.extend(
                line
                for line in self.sticker_policy.grant(
                    str(reward.value), unlock=reward.kind == NativeRewardKind.STICKER_UNLOCK, result="tempVar0"
                )
            )
            lines.extend(["if ( tempVar0 ) {", f"\t{delivered} *= true;", "}"])
        elif reward.kind == NativeRewardKind.PAGE:
            lines.append("tempVar0 = rando_page_grant*();")
            lines.extend(["if ( tempVar0 ) {", f"\t{delivered} *= true;", "}"])
        elif reward.kind == NativeRewardKind.ITEM:
            native_item = reward.value
            lines.extend(
                [
                    f'tempVar0 = rando_item_grant*("{native_item}");',
                    "if ( tempVar0 ) {",
                    f"\t{delivered} *= true;",
                    "}",
                ]
            )
        else:
            if reward.kind == NativeRewardKind.COINS:
                lines.append(f"pouch_add_coin*({reward.value});")
            elif reward.kind == NativeRewardKind.ABILITY:
                lines.extend(self.ability_grant(str(reward.value)))
            elif reward.kind == NativeRewardKind.STAGE_ACCESS:
                lines.append(f"gf_rando_stage_{str(reward.value).lower()} *= true;")
            elif reward.kind == NativeRewardKind.DOOR_ACCESS:
                lines.append(f"gf_rando_door_{str(reward.value).lower()} *= true;")
            elif reward.kind == NativeRewardKind.BOSS_ACCESS:
                lines.append(f"gf_rando_boss_{reward.value} *= true;")
            elif reward.kind == NativeRewardKind.ROYAL:
                lines.append(f"pouch_set_royal_seal*(pouch_royal_w{reward.value});")
                if self.shuffle_royals:
                    lines.append(f"gf_rando_royal_{reward.value} *= true;")
            elif reward.kind == NativeRewardKind.VICTORY:
                lines.append("gf_rando_victory *= true;")
            elif reward.kind == NativeRewardKind.MINI_STAR:
                lines.extend(
                    [
                        f'mobj_set_gf*("{reward.value}");',
                        f'wm_set_gf*("{reward.value}");',
                    ]
                )
            lines.append(f"{delivered} *= true;")
        return lines

    def delivery_body(self) -> str:
        lines = ["\ttemp tempVar0 = rando_seed_valid*();", "\tif ( tempVar0 == false ) {", "\t\treturn*;", "\t}"]
        if self.ability_mode:
            lines.extend(
                [
                    "\tif ( gf_rando_abilities_initialized == false ) {",
                    "\t\ttempVar0 = pouch_hammer | pouch_lucie;",
                    "\t\tpouch_detach_accessory*(tempVar0);",
                    "\t\tgf_rando_abilities_initialized *= true;",
                    "\t}",
                ]
            )
        if any(isinstance(check, BannerReward) for check in self.checks):
            lines.append("\ttemp tempVar1;")
        if self.album_pages is not None:
            lines.append("\tif ( gf_rando_album_initialized == false ) {")
            if self.album_pages == AlbumPages.ALL_AT_START:
                lines.extend(['\t\titem_try_addpouch*("SL_PAGE", true);'] * 6)
            lines.extend(["\t\tgf_rando_album_initialized *= true;", "\t}"])
        if self.remote_rewards:
            lines.append("\trando_remote*();")
        for reward, delivered in zip(self.starting_rewards, self.starting_flags, strict=True):
            lines.append(f"\tif ( {delivered} == false ) {{")
            lines.extend("\t\t" + line.replace("\n", "\n\t\t") for line in self.grant_body(reward, delivered))
            lines.append("\t}")
        for index, check in enumerate(self.checks):
            checked, delivered = self.receipt(index)
            if isinstance(check, BannerReward):
                lines.extend(
                    [
                        f"\ttempVar0 = pouch_honor_get_value*(honor_id_{check.honor});",
                        f"\ttempVar1 = pouch_honor_get_max*(honor_id_{check.honor});",
                    ]
                )
                factor = 10 if check.mode == Banners.REDUCED else 1
                lines.extend(
                    [f"\tif ( tempVar1 > 0 && tempVar0 * {factor} >= tempVar1 ) {{", f"\t\t{checked} *= true;", "\t}"]
                )
            if check.reward.kind in {NativeRewardKind.REMOTE, NativeRewardKind.EVENT}:
                # Collection is exported to AP; only the incoming mailbox grants
                # items. There is no local delivery receipt to allocate or set.
                # Keep its source linked in the compiler's flag-reference table.
                lines.append(f"\ttempVar0 = {checked};")
                continue
            lines.append(f"\tif ( {checked} && {delivered} == false ) {{")
            reward = check.reward
            lines.extend("\t\t" + line.replace("\n", "\n\t\t") for line in self.grant_body(reward, delivered))
            lines.append("\t}")
        return "\n".join(lines)

    def goal_block_body(self) -> str:
        lines = [
            "\ttemp tempVar5 = rando_seed_valid*();",
            "\tif ( tempVar5 == false ) {\n\t\treturn*;\n\t}",
            '\ttemp tempVar2 = "mario";',
            "\tplayer_event_flg_on*(tempVar2, event_exit);",
            "\tlocal localVar1 = mobj_check_flag*(tempVar0);",
            "\ttemp tempVar3 = false;",
            "\ttemp tempVar4 = pouch_get_map_name*();",
        ]
        # A received destination route must not pre-collect its source check.
        # Conversely revisiting an already collected check must not increment
        # the comet banner count again merely because its route remains locked.
        for index, check in enumerate(self.checks):
            if not isinstance(check, GoalBlockReward):
                continue
            checked, _ = self.receipt(index)
            lines.extend(
                [
                    f'\tif ( tempVar4 == "{check.map_name}" && tempVar1 == "{check.source_flag}" ) {{',
                    f"\t\tlocalVar1 = {checked};",
                    "\t\ttempVar3 = true;",
                    "\t}",
                ]
            )
        lines.append("\tif ( localVar1 == false ) {")
        for index, check in enumerate(self.checks):
            if not isinstance(check, GoalBlockReward):
                continue
            checked, _ = self.receipt_flags(index)
            lines.extend(
                [
                    f'\t\tif ( tempVar4 == "{check.map_name}" && tempVar1 == "{check.source_flag}" ) {{',
                    f"\t\t\t{checked} *= true;",
                    "\t\t\ttempVar3 = true;",
                    "\t\t}",
                ]
            )
        lines.extend(
            [
                "\t\trando_deliver*();",
                "\t\tif ( tempVar3 == false ) {",
                "\t\t\tmobj_set_gf*(tempVar1);",
                "\t\t\twm_set_gf*(tempVar1);",
                "\t\t}",
                "\t\tpouch_add_comet_num*();",
                "\t}",
                "\tsleep_frames* 2;",
                "\tmobj_reaction_wait*(tempVar0);",
            ]
        )
        return "\n".join(lines)

    def pickup_function(self) -> str:
        lines = [
            "private rando_pickup(temp tempVar0)  {",
            "\ttemp tempVar1 = rando_seed_valid*();",
            "\tif ( tempVar1 == false ) {\n\t\treturn* -1;\n\t}",
            "\ttemp tempVar2 = pouch_get_map_name*();",
        ]
        for index, check in enumerate(self.checks):
            if not isinstance(check, PickupReward):
                continue
            checked, _ = self.receipt_flags(index)
            lines.extend(
                [
                    f'\tif ( tempVar2 == "{check.map_name}" && tempVar0 == "{check.object_name}" ) {{',
                    f"\t\t{checked} *= true;",
                    "\t\trando_deliver*();",
                    "\t\treturn* true;",
                    "\t}",
                ]
            )
        lines.extend(["\treturn* false;", "}"])
        return "\n".join(lines) + "\n"

    def piece_pickup_function(self) -> str:
        # Story callbacks call item_get_evt_piece directly rather than the
        # ordinary map_piece_get wrapper. Its argument is the field item ID.
        pieces = [
            (index, check)
            for index, check in enumerate(self.checks)
            if isinstance(check, (PickupReward, ContainerReward)) and check.source_item.startswith("PK_FIELD_")
        ]
        identities = [(check.map_name, check.source_item) for _, check in pieces]
        if len(identities) != len(set(identities)):
            raise ValueError("Direct scrap acquisition needs an unambiguous item within each room")
        lines = [
            "private rando_piece_pickup(temp tempVar0)  {",
            "\ttemp tempVar1 = rando_seed_valid*();",
            "\tif ( tempVar1 == false ) {\n\t\treturn* -1;\n\t}",
            "\ttemp tempVar2 = pouch_get_map_name*();",
        ]
        for index, check in pieces:
            checked, _ = self.receipt(index)
            lines += [
                f'\tif ( tempVar2 == "{check.map_name}" && tempVar0 == "{check.source_item}" ) {{',
                f"\t\t{checked} *= true;",
                "\t\trando_deliver*();",
                "\t\treturn* true;",
                "\t}",
            ]
        return "\n".join(lines + ["\treturn* false;", "}"]) + "\n"

    def polling_function(self) -> str:
        return "private rando_delivery_poll()  {\n\twhile* 1 {\n\t\trando_deliver*();\n\t\tsleep_frames* 30;\n\t}\n}\n"
