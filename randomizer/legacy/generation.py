from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import math
import random
from .catalog import JsonObject, Settings, requirement_met, validate_catalog


def enabled_checks(catalog: JsonObject, settings: Settings) -> list[JsonObject]:
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
            spheres, unreachable, goal = playthrough(catalog, checks, placements)
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
        "Could not generate a reachable seed; check the catalog and starting inventory"
    )
