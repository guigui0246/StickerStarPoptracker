"""Strict JSON boundary for typed game definitions."""

from __future__ import annotations

import json
import sys
from pathlib import Path as FilePath
from typing import TypeAlias
from ..domain import (
    EndGoal,
    Event,
    GameDefinition,
    Goal,
    Item,
    Location,
    Path,
    Region,
    Rules,
    StartingRegion,
    Vector,
)

Json: TypeAlias = None | bool | int | float | str | list["Json"] | dict[str, "Json"]


def obj(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def array(value: Json) -> list[Json]:
    if not isinstance(value, list):
        raise ValueError("Expected a JSON array")
    return value


def string(value: Json) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a nonempty string")
    return value


def fields(data: dict[str, Json], required: set[str], optional: set[str] | frozenset[str] = frozenset()) -> None:
    missing, unknown = required - data.keys(), data.keys() - required - optional
    if missing or unknown:
        raise ValueError(f"Invalid catalog fields: missing {sorted(missing)}, unknown {sorted(unknown)}")


def unique_object(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    result: dict[str, Json] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate catalog JSON field: {name}")
        result[name] = value
    return result


def load_catalog_data(path: FilePath) -> dict[str, Json]:
    if path.resolve() == python_game_directory().resolve():
        from .game import game_definition

        return encode_catalog(game_definition())
    if path.is_dir():
        # Split authoring files keep checks, rewards and physical links easy to
        # find. Their combined object uses the same strict catalog boundary.
        return {
            "format_version": 2,
            **{
                name: array(json.loads((path / (name + ".json")).read_text(encoding="utf-8-sig"),
                                       object_pairs_hook=unique_object))
                for name in ("items", "locations", "regions", "paths", "pool", "starting_items")
            },
        }
    return obj(json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object))


def parse_rules(value: Json) -> Rules:
    data = obj(value)
    if len(data) != 1:
        raise ValueError("A rule needs exactly one predicate")
    if "item" in data:
        return Rules.has(string(data["item"]))
    if "count" in data:
        values = array(data["count"])
        if len(values) != 2 or type(values[1]) is not int:
            raise ValueError("count requires [item ID, positive integer]")
        return Rules.has(string(values[0]), values[1])
    for operator in ("all", "any"):
        if operator in data:
            children = tuple(parse_rules(child) for child in array(data[operator]))
            return Rules.all_of(*children) if operator == "all" else Rules.any_of(*children)
    raise ValueError("Unknown rule predicate")


def load_catalog(path: FilePath) -> GameDefinition:
    if path.resolve() == python_game_directory().resolve():
        from .game import game_definition

        return game_definition()
    return parse_catalog(load_catalog_data(path))


def python_game_directory() -> FilePath:
    """Location used to select the bundled Python authoring package."""
    if getattr(sys, "frozen", False):
        return FilePath(getattr(sys, "_MEIPASS")) / "bundled" / "game"
    return FilePath(__file__).with_name("game")


def encode_rules(rule: Rules) -> Json:
    if rule.operator == "item":
        return {"item": rule.item_id} if rule.amount == 1 else {"count": [rule.item_id, rule.amount]}
    return {rule.operator: [encode_rules(child) for child in rule.children]}


def encode_catalog(game: GameDefinition) -> dict[str, Json]:
    """Serialize typed objects only at patch/tracker/JSON interchange boundaries."""
    items: list[Json] = []
    for item in game.items:
        row: dict[str, Json] = {"id": item.id, "name": item.name, "progression": item.progression}
        if isinstance(item, Event):
            row["location"] = item.location_id
        items.append(row)
    locations: list[Json] = []
    for location in game.locations:
        row = {"id": location.id, "name": location.name, "region": location.region_id,
               "requires": encode_rules(location.rules)}
        if isinstance(location, Goal):
            row.update({"type": "end_goal" if isinstance(location, EndGoal) else "goal", "item": location.item.id})
        locations.append(row)
    return {
        "format_version": 2,
        "items": items,
        "locations": locations,
        "regions": [{"id": region.id, "name": region.name,
                     **({"starting": True} if isinstance(region, StartingRegion) else {})} for region in game.regions],
        "paths": [
            {"id": path.id,
             "forward": {"source": path.forward.source, "target": path.forward.target,
                         "requires": encode_rules(path.forward.rules)},
             "reverse": {"source": path.reverse.source, "target": path.reverse.target,
                         "requires": encode_rules(path.reverse.rules)}}
            for path in game.paths
        ],
        "pool": list(game.pool),
        "starting_items": list(game.starting_items),
    }


def parse_catalog(value: Json) -> GameDefinition:
    data = obj(value)
    fields(data, {"format_version", "items", "regions", "locations", "paths", "pool"}, {"starting_items"})
    if type(data["format_version"]) is not int or data["format_version"] != 2:
        raise ValueError("Typed catalogs require format_version 2")
    items: list[Item] = []
    for raw in array(data["items"]):
        item = obj(raw)
        fields(item, {"id", "name"}, {"progression", "location"})
        progression = item.get("progression", True)
        if type(progression) is not bool:
            raise ValueError("progression must be boolean")
        item_args = (string(item["id"]), string(item["name"]), progression)
        items.append(Event(*item_args, location_id=string(item["location"])) if "location" in item else Item(*item_args))
    by_id = {item.id: item for item in items}
    regions: list[Region] = []
    for raw in array(data["regions"]):
        region = obj(raw)
        fields(region, {"id", "name"}, {"starting"})
        starting = region.get("starting", False)
        if type(starting) is not bool:
            raise ValueError("starting must be boolean")
        region_class = StartingRegion if starting else Region
        regions.append(region_class(string(region["id"]), string(region["name"])))
    locations: list[Location] = []
    for raw in array(data["locations"]):
        loc = obj(raw)
        fields(loc, {"id", "name", "region"}, {"type", "requires", "item"})
        location_args = (
            string(loc["id"]),
            string(loc["name"]),
            string(loc["region"]),
            parse_rules(loc.get("requires", {"all": []})),
        )
        kind = string(loc.get("type", "location"))
        if kind == "location":
            if "item" in loc:
                raise ValueError("Fixed location rewards require a Goal or an Event declaration")
            locations.append(Location(*location_args))
        elif kind in {"goal", "end_goal"}:
            if "item" not in loc:
                raise ValueError("Goals require a fixed item")
            reward = string(loc["item"])
            if reward not in by_id:
                raise ValueError("Unknown goal reward")
            goal_class = EndGoal if kind == "end_goal" else Goal
            locations.append(goal_class(*location_args, by_id[reward]))
        else:
            raise ValueError("Unknown location type")
    paths: list[Path] = []
    for raw in array(data["paths"]):
        path_data = obj(raw)
        fields(path_data, {"id", "forward", "reverse"})
        vectors = []
        for direction in ("forward", "reverse"):
            vector = obj(path_data[direction])
            fields(vector, {"source", "target"}, {"requires"})
            vectors.append(
                Vector(
                    string(vector["source"]),
                    string(vector["target"]),
                    parse_rules(vector.get("requires", {"all": []})),
                )
            )
        paths.append(Path(string(path_data["id"]), *vectors))
    return GameDefinition(
        tuple(items),
        tuple(regions),
        tuple(locations),
        tuple(paths),
        tuple(string(item) for item in array(data["pool"])),
        tuple(string(item) for item in array(data.get("starting_items", []))),
    )
