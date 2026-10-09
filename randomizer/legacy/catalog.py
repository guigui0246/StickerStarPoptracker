from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

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
            raise ValueError("banners must be boolean; banner_divisor must be 1 or 10")


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
        return set[str]().union(*(requirement_items(child) for child in next(iter(rule.values()))))
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
        if item["kind"] == "coins" and (type(item.get("amount")) is not int or item["amount"] < 1):
            raise ValueError(f"Invalid coin amount: {item_id}")
    for check in checks:
        if check["kind"] not in CHECK_KINDS:
            raise ValueError(f"Unknown check kind: {check['id']}")
        if check["kind"] == "banner" and (type(check.get("threshold")) is not int or check["threshold"] < 1):
            raise ValueError(f"Invalid banner threshold: {check['id']}")
    rules = [c.get("requires", {"all": []}) for c in checks] + [catalog["goal"]]
    referenced = set[str]().union(*(requirement_items(r) for r in rules))
    referenced.update(catalog.get("starting_items", []))
    referenced.update(catalog["progression_pool"])
    referenced.update(catalog.get("filler_pool", []))
    if referenced - items.keys():
        raise ValueError(f"Unknown item IDs: {sorted(referenced - items.keys())}")
    for item_id in catalog["progression_pool"]:
        if items[item_id]["kind"] in ("coins", "sticker_copy"):
            raise ValueError("Consumable fillers cannot provide progression logic")
    pool = set(catalog["progression_pool"]) | set(catalog.get("starting_items", []))
    if set[str]().union(*(requirement_items(r) for r in rules)) - pool:
        raise ValueError("Every logic item must be in the progression pool or starting inventory")
