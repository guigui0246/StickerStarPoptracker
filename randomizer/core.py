"""Game-independent seed and reward logic using the standard library."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
import random
from typing import Any, Self, cast

JsonObject = dict[str, Any]

KINDS = {
    "thing",
    "royal",
    "hammer",
    "paperization",
    "mini_star",
    "door_place",
    "generic_sticker",
    "boss_unlock",
    "scrap",
    "coins",
    "sticker_copy",
}
CHECK_KINDS = {
    "mini_star",
    "thing",
    "boss",
    "kamek",
    "enemy",
    "banner",
    "scrap",
    "shop",
    "museum",
}


@dataclass(frozen=True)
class Settings:
    banners: bool = True
    banner_divisor: int = 1

    def __post_init__(self) -> None:
        if type(self.banners) is not bool or self.banner_divisor not in (
            1,
            10,
        ):
            raise ValueError(
                "banners must be boolean; banner_divisor must be 1 or 10"
            )


def requirement_met(rule: object, inventory: Mapping[str, int]) -> bool:
    if not isinstance(rule, dict):
        raise ValueError("A requirement must contain exactly one predicate")
    rule = cast(JsonObject, rule)
    if len(rule) != 1:
        raise ValueError("A requirement must contain exactly one predicate")
    if "all" in rule or "any" in rule:
        key = next(iter(rule))
        if not isinstance(rule[key], list):
            raise ValueError("all/any require lists")
        results = [requirement_met(child, inventory) for child in rule[key]]
        return all(results) if key == "all" else any(results)
    if "item" in rule:
        return inventory[rule["item"]] > 0
    if "count" in rule:
        item, count = rule["count"]
        if type(count) is not int or count < 1:
            raise ValueError("Item counts must be positive integers")
        return inventory[item] >= count
    raise ValueError(f"Unsupported requirement: {rule}")


def requirement_items(rule: JsonObject) -> set[str]:
    requirement_met(rule, Counter())  # Validate even unreachable branches.
    if "all" in rule or "any" in rule:
        return set[str]().union(
            *(requirement_items(child) for child in next(iter(rule.values())))
        )
    return {rule["item"] if "item" in rule else rule["count"][0]}


def validate_catalog(catalog: JsonObject) -> None:
    items = catalog["items"]
    checks = catalog["checks"]
    if len({c["id"] for c in checks}) != len(checks):
        raise ValueError("Duplicate check IDs")
    for item_id, item in items.items():
        if item["kind"] not in KINDS:
            raise ValueError(f"Unknown reward kind: {item_id}")
        if item["kind"] in (
            "thing",
            "generic_sticker",
            "sticker_copy",
        ) and not item.get("sticker"):
            raise ValueError(f"Missing sticker ID: {item_id}")
        if item["kind"] == "coins" and (
            type(item.get("amount")) is not int or item["amount"] < 1
        ):
            raise ValueError(f"Invalid coin amount: {item_id}")
    for check in checks:
        if check["kind"] not in CHECK_KINDS:
            raise ValueError(f"Unknown check kind: {check['id']}")
        if check["kind"] == "banner" and (
            type(check.get("threshold")) is not int or check["threshold"] < 1
        ):
            raise ValueError(f"Invalid banner threshold: {check['id']}")
    rules = [c.get("requires", {"all": []}) for c in checks] + [
        catalog["goal"]
    ]
    referenced = set[str]().union(*(requirement_items(r) for r in rules))
    referenced.update(catalog.get("starting_items", []))
    referenced.update(catalog["progression_pool"])
    referenced.update(catalog.get("filler_pool", []))
    if referenced - items.keys():
        raise ValueError(
            f"Unknown item IDs: {sorted(referenced - items.keys())}"
        )
    for item_id in catalog["progression_pool"]:
        if items[item_id]["kind"] in ("coins", "sticker_copy"):
            raise ValueError(
                "Consumable fillers cannot provide progression logic"
            )
    pool = set(catalog["progression_pool"]) | set(
        catalog.get("starting_items", [])
    )
    if set[str]().union(*(requirement_items(r) for r in rules)) - pool:
        raise ValueError(
            "Every logic item must be in the progression pool "
            "or starting inventory"
        )


def enabled_checks(
    catalog: JsonObject, settings: Settings
) -> list[JsonObject]:
    result: list[JsonObject] = []
    for original in catalog["checks"]:
        if original["kind"] == "banner" and not settings.banners:
            continue
        check: JsonObject = dict(original)
        if check["kind"] == "banner":
            check["threshold"] = max(
                1, math.ceil(check["threshold"] / settings.banner_divisor)
            )
        result.append(check)
    return result


def playthrough(
    catalog: JsonObject,
    checks: list[JsonObject],
    placements: Mapping[str, str],
) -> tuple[list[list[str]], list[str], bool]:
    inventory: Counter[str] = Counter(catalog.get("starting_items", []))
    remaining = {c["id"]: c for c in checks}
    spheres: list[list[str]] = []
    while remaining:
        reachable = sorted(
            key
            for key, check in remaining.items()
            if requirement_met(check.get("requires", {"all": []}), inventory)
        )
        if not reachable:
            break
        spheres.append(reachable)
        for key in reachable:
            inventory[placements[key]] += 1
            del remaining[key]
    return (
        spheres,
        sorted(remaining),
        requirement_met(catalog["goal"], inventory),
    )


def generate(
    catalog: JsonObject,
    seed: str | int,
    settings: Settings = Settings(),
    attempts: int = 200,
) -> JsonObject:
    validate_catalog(catalog)
    checks = enabled_checks(catalog, settings)
    progression = catalog["progression_pool"]
    if len(progression) > len(checks):
        raise ValueError("More progression rewards than enabled checks")
    fillers = catalog.get("filler_pool", [])
    if len(progression) < len(checks) and not fillers:
        raise ValueError("A filler pool is required for unused checks")
    rng = random.Random(str(seed))
    for _ in range(attempts):
        remaining = list(checks)
        inventory: Counter[str] = Counter(catalog.get("starting_items", []))
        rewards = list(progression)
        rng.shuffle(rewards)
        placements: dict[str, str] = {}
        for item_id in rewards:
            reachable = [
                c
                for c in remaining
                if requirement_met(c.get("requires", {"all": []}), inventory)
            ]
            if not reachable:
                break
            check = rng.choice(reachable)
            remaining.remove(check)
            placements[check["id"]] = item_id
            inventory[item_id] += 1
        else:
            for check in remaining:
                placements[check["id"]] = rng.choice(fillers)
            spheres, unreachable, goal = playthrough(
                catalog, checks, placements
            )
            if not unreachable and goal:
                return {
                    "format_version": 1,
                    "seed": str(seed),
                    "catalog_sha256": hashlib.sha256(
                        json.dumps(catalog, sort_keys=True).encode()
                    ).hexdigest(),
                    "settings": {
                        "banners": settings.banners,
                        "banner_divisor": settings.banner_divisor,
                    },
                    "checks": checks,
                    "placements": placements,
                    "spheres": spheres,
                }
    raise ValueError(
        "Could not generate a reachable seed; "
        "check the catalog and starting inventory"
    )


@dataclass
class RewardState:
    inventory: Counter[str] = field(default_factory=Counter[str])
    sticker_inventory: Counter[str] = field(default_factory=Counter[str])
    generic_unlocks: set[str] = field(default_factory=set[str])
    thing_shop_unlocks: set[str] = field(default_factory=set[str])
    completed_checks: set[str] = field(default_factory=set[str])
    coins: int = 0

    def ordinary_sticker(self, sticker: str) -> str:
        delivered = (
            sticker if sticker in self.generic_unlocks else "kamek_flip_flop"
        )
        self.sticker_inventory[delivered] += 1
        return delivered

    def deliver(
        self, check_id: str, reward_id: str, items: Mapping[str, JsonObject]
    ) -> bool:
        if check_id in self.completed_checks:
            return False
        reward = items[reward_id]
        kind = reward["kind"]
        if kind not in KINDS:
            raise ValueError(f"Unsupported reward kind: {kind}")
        if kind == "generic_sticker":
            self.generic_unlocks.add(reward["sticker"])
            self.sticker_inventory[reward["sticker"]] += 1
        elif kind == "thing":
            self.thing_shop_unlocks.add(reward["sticker"])
            self.sticker_inventory[reward["sticker"]] += 1
        elif kind == "sticker_copy":
            self.ordinary_sticker(reward["sticker"])
        elif kind == "coins":
            self.coins += reward["amount"]
        self.inventory[reward_id] += 1
        self.completed_checks.add(check_id)
        return True

    def shop_sells(self, sticker: str, thing: bool = False) -> bool:
        return sticker in (
            self.thing_shop_unlocks if thing else self.generic_unlocks
        )

    def to_save(self) -> JsonObject:
        return {
            "inventory": dict(self.inventory),
            "sticker_inventory": dict(self.sticker_inventory),
            "generic_unlocks": sorted(self.generic_unlocks),
            "thing_shop_unlocks": sorted(self.thing_shop_unlocks),
            "completed_checks": sorted(self.completed_checks),
            "coins": self.coins,
        }

    @classmethod
    def from_save(cls, data: JsonObject) -> Self:
        return cls(
            Counter(data["inventory"]),
            Counter(data["sticker_inventory"]),
            set(data["generic_unlocks"]),
            set(data["thing_shop_unlocks"]),
            set(data["completed_checks"]),
            data["coins"],
        )
