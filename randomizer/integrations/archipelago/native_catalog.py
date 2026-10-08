"""Asset-free native catalog bundles and stable AP registries.

A bundle supplies a caller-authored graph; this module does not infer puzzles
from tracker placeholders or assert that an incomplete graph covers the game.
"""

from dataclasses import dataclass

from ...data.catalog import Json, obj, parse_catalog, string
from ...domain import GameDefinition
from ..rom.native_generation import NativeBindings, catalog_digest
from ..rom.native_delivery import NativeRewardKind
from ..rom.plan_io import decode_sticker_policy
from ..rom.stickers import StickerPolicy
from .runtime import integer

ITEM_BASE = 0x53530000
LOCATION_BASE = 0x53538000
REGISTRY_END = 0x53540000


@dataclass(frozen=True)
class NativeAPRegistry:
    items: dict[str, int]
    locations: dict[str, int]

    def __post_init__(self) -> None:
        for values, lower, upper in ((self.items, ITEM_BASE, LOCATION_BASE), (self.locations, LOCATION_BASE, REGISTRY_END)):
            if any(not isinstance(key, str) or not key or type(value) is not int or not lower <= value < upper for key, value in values.items()):
                raise ValueError("Invalid native AP identifier namespace")
            if len(set(values.values())) != len(values):
                raise ValueError("Native AP identifiers cannot be reused")

    def validate(self, game: GameDefinition) -> None:
        fixed = set(game.fixed_rewards.values())
        if {item.id for item in game.items if item.id not in fixed} - self.items.keys():
            raise ValueError("The AP registry does not cover every catalog item")
        if {location.id for location in game.locations if location.id not in game.fixed_rewards} - self.locations.keys():
            raise ValueError("The AP registry does not cover every randomized location")

    @classmethod
    def parse(cls, value: Json) -> "NativeAPRegistry":
        data = obj(value)
        if set(data) != {"format_version", "items", "locations"} or type(data["format_version"]) is not int or data["format_version"] != 1:
            raise ValueError("Unsupported native AP registry")
        return cls({key: integer(value) for key, value in obj(data["items"]).items()},
                   {key: integer(value) for key, value in obj(data["locations"]).items()})

    def encode(self) -> Json:
        return {"format_version": 1, "items": dict(self.items), "locations": dict(self.locations)}


def allocate_registry(game: GameDefinition, previous: NativeAPRegistry | None = None) -> NativeAPRegistry:
    """Append new IDs; retain removed entries so an ID is never recycled."""
    items = dict(previous.items) if previous else {}
    locations = dict(previous.locations) if previous else {}
    fixed = set(game.fixed_rewards.values())
    for values, identifiers, first in (
        (items, {item.id for item in game.items if item.id not in fixed}, ITEM_BASE),
        (locations, {location.id for location in game.locations if location.id not in game.fixed_rewards}, LOCATION_BASE),
    ):
        next_id = max(values.values(), default=first - 1) + 1
        for identifier in sorted(identifiers - values.keys()):
            values[identifier] = next_id
            next_id += 1
    registry = NativeAPRegistry(items, locations)
    registry.validate(game)
    return registry


@dataclass(frozen=True)
class NativeAPCatalog:
    game: GameDefinition
    bindings: NativeBindings
    registry: NativeAPRegistry
    rom_sha256: str
    catalog_hash: str
    sticker_policy: StickerPolicy | None

    @classmethod
    def parse(cls, value: Json) -> "NativeAPCatalog":
        data = obj(value)
        if set(data) != {"format_version", "catalog", "bindings", "registry", "rom_sha256", "sticker_policy"} or type(data["format_version"]) is not int or data["format_version"] != 1:
            raise ValueError("Unsupported native AP catalog bundle")
        game = parse_catalog(data["catalog"])
        bindings = NativeBindings.parse(data["bindings"], data["catalog"])
        bindings.validate(game)
        registry = NativeAPRegistry.parse(data["registry"])
        registry.validate(game)
        source_hash = string(data["rom_sha256"])
        if len(source_hash) != 64 or any(character not in "0123456789abcdef" for character in source_hash):
            raise ValueError("The native AP bundle requires the target ROM SHA-256")
        policy = decode_sticker_policy(data["sticker_policy"])
        sticker_rewards = [reward for reward in bindings.items.values() if reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}]
        if sticker_rewards and policy is None:
            raise ValueError("Native sticker catalogs require their ROM-derived sticker policy")
        if policy is not None:
            recognized = set(policy.generic) | {sticker for sticker, _ in policy.things}
            if any(reward.value not in recognized for reward in sticker_rewards):
                raise ValueError("A catalog sticker reward is absent from its native policy")
        return cls(game, bindings, registry, source_hash, catalog_digest(value), policy)
