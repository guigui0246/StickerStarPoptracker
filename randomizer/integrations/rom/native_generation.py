"""Bind a solved typed catalog seed to explicit, observed native checks.

The binding file supplies native identities; it never infers access rules.
This bridge does not turn an unverified catalog into verified game logic.
"""

from dataclasses import dataclass, replace
from collections import Counter
import hashlib
import json
from pathlib import Path

from ...data.catalog import Json, array, load_catalog_data, obj, parse_catalog, string
from ...domain import EndGoal, GameDefinition, Rules
from ...settings import AlbumPages, Banners, DoorStickers, EnemyRewards, GenericStickers, Museum, Settings
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
        if path.is_dir():
            # Only logic may change relative to the shipped source registry.
            # Validate its reference before rebinding edited authoring files.
            original = load_catalog_data(path / "native_reference.json")
            bound = cls.parse(load_catalog_data(path / "bindings.json"), original)
            bound.validate(parse_catalog(original))
            updated = replace(bound, catalog_hash=catalog_digest(catalog))
            updated.validate(parse_catalog(catalog))
            return updated
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
        boolean_kinds = {
            NativeRewardKind.ABILITY, NativeRewardKind.STAGE_ACCESS, NativeRewardKind.DOOR_ACCESS,
            NativeRewardKind.BOSS_ACCESS, NativeRewardKind.MINI_STAR, NativeRewardKind.ROYAL,
            NativeRewardKind.EVENT, NativeRewardKind.VICTORY,
        }
        capabilities = {identifier: reward for identifier, reward in self.items.items() if reward.kind in boolean_kinds}
        if len(set(capabilities.values())) != len(capabilities):
            raise ValueError("Idempotent native capabilities require one catalog identity, not separate aliases")

        def validate_counts(rule: Rules) -> None:
            if rule.operator == "item" and rule.item_id in capabilities and rule.amount != 1:
                raise ValueError("Boolean native ownership cannot satisfy a counted requirement above one")
            for child in rule.children:
                validate_counts(child)

        for location in game.locations:
            validate_counts(location.rules)
        for path in game.paths:
            validate_counts(path.forward.rules)
            validate_counts(path.reverse.rules)
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
    shuffle_royals = shuffle_royals or any(
        bindings.items[identifier].kind == NativeRewardKind.ROYAL for identifier in game.pool + game.starting_items
    )
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
        album_pages=None if settings.album_pages == AlbumPages.VANILLA else settings.album_pages,
        shuffle_royals=shuffle_royals,
        seed_name=seed.seed,
        starting_rewards=tuple(bindings.items[item] for item in game.starting_items),
        catalog_hash=bindings.catalog_hash,
        vanilla_generic_stickers=settings.generic_stickers == GenericStickers.DISABLED,
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
    removed = set()
    for identifier, source in bindings.locations.items():
        if isinstance(source, BannerReward) and settings.banners == Banners.OFF:
            removed.add(identifier)
        if isinstance(source, EnemyReward) and settings.enemy_rewards == EnemyRewards.OFF:
            # Boss admission and Royal reward checks are separate sources and
            # remain enabled. Enemy first-victory checks are the optional pool.
            removed.add(identifier)
        if isinstance(source, FlagReward) and source.category == "museum":
            things = source.source_flag.startswith("gf_museum_robj_")
            if (settings.museum == Museum.OFF or (settings.museum == Museum.NORMAL and things)
                    or (settings.museum == Museum.THINGS and not things)):
                removed.add(identifier)
    if removed & game.fixed_rewards.keys():
        raise ValueError("Check settings cannot remove fixed events or goals")
    remaining = tuple(location for location in game.locations if location.id not in removed)
    paths = game.paths
    copies = {str(native.value): identifier for identifier, native in bindings.items.items()
              if native.kind == NativeRewardKind.STICKER_COPY}
    generic = {identifier for identifier, native in bindings.items.items()
               if native.kind == NativeRewardKind.STICKER_UNLOCK and str(native.value) in copies}
    if settings.generic_stickers == GenericStickers.DISABLED:
        def available_in_vanilla(rule: Rules) -> Rules:
            # These predicates represent unlock entitlements, not a physical
            # inventory count. Vanilla shops make the entitlement unconditional.
            if rule.operator == "item" and rule.item_id in generic:
                return Rules.all_of()
            return replace(rule, children=tuple(available_in_vanilla(child) for child in rule.children))

        remaining = tuple(replace(location, rules=available_in_vanilla(location.rules)) for location in remaining)
        paths = tuple(replace(path, forward=replace(path.forward, rules=available_in_vanilla(path.forward.rules)),
                              reverse=replace(path.reverse, rules=available_in_vanilla(path.reverse.rules))) for path in paths)
    required = set().union(
        *(location.rules.referenced_items() for location in remaining),
        *(vector.rules.referenced_items() for path in paths for vector in (path.forward, path.reverse)),
    )
    items = {item.id: item for item in game.items}
    pool = list(game.pool)
    starting = list(game.starting_items)
    if settings.generic_stickers == GenericStickers.DISABLED:
        fillers = sorted(key for key, item in items.items() if not item.progression and key not in required
                         and bindings.items[key].kind == NativeRewardKind.COINS)
        if generic and not fillers:
            raise ValueError("Vanilla generic stickers require a coin filler")
        pool = [fillers[0] if identifier in generic else identifier for identifier in pool]
        starting = [copies[str(bindings.items[identifier].value)] if identifier in generic else identifier
                    for identifier in starting]
    if settings.door_stickers == DoorStickers.VANILLA:
        # Move place capabilities out of the shuffled pool while retaining all
        # native gates. Idempotent starting grants unlock places without giving
        # a Secret Door sticker or satisfying any other puzzle prerequisite.
        for index, identifier in enumerate(pool):
            if bindings.items[identifier].kind == NativeRewardKind.DOOR_ACCESS:
                if identifier not in starting:
                    starting.append(identifier)
                fillers = [key for key, item in items.items() if not item.progression and key not in required
                           and bindings.items[key].kind == NativeRewardKind.COINS]
                if not fillers:
                    raise ValueError("Vanilla door places require a coin filler")
                pool[index] = sorted(fillers)[0]
    for _ in removed:
        candidates = [
            index for index, identifier in enumerate(pool) if not items[identifier].progression and identifier not in required
        ]
        if not candidates:
            raise ValueError("Removing checks requires enough surplus filler; progression rewards cannot be dropped")
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
    enabled = replace(game, locations=remaining, paths=paths, pool=tuple(pool), starting_items=tuple(starting))
    sources = {identifier: source for identifier, source in bindings.locations.items() if identifier not in removed}
    return enabled, replace(bindings, locations=sources)
