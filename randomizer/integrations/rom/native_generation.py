"""Bind a solved typed catalog seed to explicit, observed native checks.

The binding file supplies native identities; it never infers access rules.
This bridge does not turn an unverified catalog into verified game logic.
"""

from dataclasses import dataclass, replace
from collections import Counter
import hashlib
import json
from pathlib import Path

from ...data.catalog import Json, array, obj, string
from ...domain import EndGoal, GameDefinition
from ...settings import AlbumPages, Banners, Settings
from ...standalone.generation import Seed, generate_seed, playthrough
from .native_delivery import (
    BannerReward,
    DeliveryPlan,
    EnemyReward,
    FlagReward,
    GoalBlockReward,
    NativeReward,
    NativeRewardKind,
    PickupReward,
    ContainerReward,
    PeelReward,
    ScriptReward,
)
from .plan_io import checks, reward

NativeCheck = (
    GoalBlockReward | PickupReward | ContainerReward | PeelReward | FlagReward | BannerReward | ScriptReward | EnemyReward
)


def catalog_digest(data: Json) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class NativeBindings:
    items: dict[str, NativeReward]
    locations: dict[str, NativeCheck]
    catalog_hash: str | None = None

    @classmethod
    def load(cls, path: Path, catalog: Json) -> "NativeBindings":
        return cls.parse(json.loads(path.read_text(encoding="utf-8")), catalog)

    @classmethod
    def parse(cls, value: Json, catalog: Json) -> "NativeBindings":
        data = obj(value)
        if (
            set(data) != {"format_version", "catalog_sha256", "items", "locations"}
            or type(data["format_version"]) is not int
            or data["format_version"] != 1
        ):
            raise ValueError("Unsupported native catalog bindings")
        if data["catalog_sha256"] != catalog_digest(catalog):
            raise ValueError("Native bindings belong to a different logic catalog")
        items = {key: reward(value) for key, value in obj(data["items"]).items()}
        locations: dict[str, NativeCheck] = {}
        for raw in array(data["locations"]):
            row = obj(raw)
            if set(row) != {"location", "source"}:
                raise ValueError("Native location bindings require location and source")
            identifier = string(row["location"])
            source = obj(row["source"])
            if identifier in locations or "reward" in source:
                raise ValueError("Duplicate location or reward embedded in a native source binding")
            # Source parsing shares the strict native-plan boundary. This dummy
            # is replaced by the generated reward before a plan can be emitted.
            dummy: dict[str, Json] = {"kind": "coins", "value": 1}
            entry: dict[str, Json] = dict(source)
            entry["reward"] = dummy
            locations[identifier] = checks([entry])[0]
        return cls(items, locations, catalog_digest(catalog))

    def validate(self, game: GameDefinition) -> None:
        if set(self.items) != {item.id for item in game.items} or set(self.locations) != {
            location.id for location in game.locations
        }:
            raise ValueError("Native bindings must cover the exact catalog item and location registries")
        if len({check.id for check in self.locations.values()}) != len(self.locations):
            raise ValueError("Two logic locations cannot share one native check")
        if any(item.kind == NativeRewardKind.REMOTE for item in self.items.values()):
            raise ValueError("Standalone catalog rewards cannot point to a network player")
        events = {identifier for identifier, reward in self.items.items() if reward.kind == NativeRewardKind.EVENT}
        if events - set(game.fixed_rewards.values()):
            raise ValueError("Native story events cannot be shuffled")
        for location in game.locations:
            item = game.fixed_rewards.get(location.id)
            if item in events:
                source = self.locations[location.id]
                if not isinstance(source, FlagReward) or source.source_flag != self.items[item].value:
                    raise ValueError("Fixed native event bindings must observe their original story flag")
            is_victory = item is not None and self.items[item].kind == NativeRewardKind.VICTORY
            if isinstance(location, EndGoal) != is_victory:
                raise ValueError("Native victory must be the fixed EndGoal reward")


def bind_seed(
    game: GameDefinition,
    seed: Seed,
    bindings: NativeBindings,
    settings: Settings = Settings(),
    *,
    shuffle_royals: bool = False,
) -> DeliveryPlan:
    bindings.validate(game)
    replay = playthrough(game, seed.placements)
    if not replay.won or sum(map(len, replay.spheres)) != len(game.locations):
        raise ValueError("Native patches require a seed whose goal and every enabled check are reachable")
    placements = seed.placements | game.fixed_rewards
    native_checks: list[NativeCheck] = []
    for location in game.locations:
        source = bindings.locations[location.id]
        if isinstance(source, BannerReward):
            if settings.banners == Banners.OFF:
                raise ValueError("Disabled banners must be removed from the catalog before generation")
            source = replace(source, mode=settings.banners)
        native_checks.append(replace(source, reward=bindings.items[placements[location.id]]))
    return DeliveryPlan(
        tuple(native_checks),
        album_pages=settings.album_pages,
        shuffle_royals=shuffle_royals,
        seed_name=seed.seed,
        starting_rewards=tuple(bindings.items[item] for item in game.starting_items),
        catalog_hash=bindings.catalog_hash,
    )


def generate_native_seed(
    game: GameDefinition, bindings: NativeBindings, seed: str, settings: Settings = Settings(), *, shuffle_royals: bool = False
) -> tuple[Seed, DeliveryPlan]:
    bindings.validate(game)
    game, bindings = configure_catalog(game, bindings, settings)
    generated = generate_seed(game, seed)
    return generated, bind_seed(game, generated, bindings, settings, shuffle_royals=shuffle_royals)


def configure_catalog(
    game: GameDefinition, bindings: NativeBindings, settings: Settings
) -> tuple[GameDefinition, NativeBindings]:
    """Apply check settings before filling, preserving every required reward.

    Removing banners may trim only surplus, non-progression pool entries that
    no access rule references. Never silently discard a progression item.
    """
    removed = (
        {identifier for identifier, source in bindings.locations.items() if isinstance(source, BannerReward)}
        if settings.banners == Banners.OFF
        else set()
    )
    if removed & game.fixed_rewards.keys():
        raise ValueError("Disabled banners cannot remove fixed events or goals")
    remaining = tuple(location for location in game.locations if location.id not in removed)
    required = set().union(
        *(location.rules.referenced_items() for location in remaining),
        *(vector.rules.referenced_items() for path in game.paths for vector in (path.forward, path.reverse)),
    )
    items = {item.id: item for item in game.items}
    pool = list(game.pool)
    for _ in removed:
        candidates = [
            index for index, identifier in enumerate(pool) if not items[identifier].progression and identifier not in required
        ]
        if not candidates:
            raise ValueError("Removing banners requires enough surplus filler; progression rewards cannot be dropped")
        pool.pop(candidates[-1])
    page_items = sorted(identifier for identifier, reward in bindings.items.items() if reward.kind == NativeRewardKind.PAGE)
    if any(game.fixed_rewards.get(location.id) in page_items for location in game.locations):
        raise ValueError("Album upgrades belong in the shuffled pool, not fixed events")
    if settings.album_pages == AlbumPages.RANDOMIZED:
        if not page_items or len(page_items) > 6:
            raise ValueError("Randomized pages require one to six catalog page item IDs")
        count = sum(identifier in page_items for identifier in pool + list(game.starting_items))
        if count > 6:
            raise ValueError("The catalog cannot contain more than six album upgrades")
        page_counts = Counter(pool + list(game.starting_items))
        for _ in range(6 - count):
            candidates = [
                index
                for index, identifier in enumerate(pool)
                if not items[identifier].progression and identifier not in required and identifier not in page_items
            ]
            if not candidates:
                raise ValueError("Randomized pages require six available rewards; progression cannot be displaced")
            identifier = min(page_items, key=lambda identifier: (page_counts[identifier], identifier))
            pool[candidates[-1]] = identifier
            page_counts[identifier] += 1
    else:
        if any(identifier in page_items for identifier in game.starting_items):
            raise ValueError("Precollected page rewards require randomized pages")
        filler = sorted(
            identifier
            for identifier, item in items.items()
            if not item.progression
            and identifier not in required
            and bindings.items[identifier].kind in {NativeRewardKind.COINS, NativeRewardKind.STICKER_COPY}
        )
        for index, identifier in enumerate(pool):
            if identifier in page_items:
                if not filler:
                    raise ValueError("All-at-start pages require a catalog filler to replace page rewards")
                pool[index] = filler[0]
    enabled = replace(game, locations=remaining, pool=tuple(pool))
    sources = {identifier: source for identifier, source in bindings.locations.items() if identifier not in removed}
    return enabled, replace(bindings, locations=sources)
