"""Check pack wiring independently of a randomizer's progression rules."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str | Path) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        node = cast(dict[str, Any], value)
        yield node
        for child in node.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in cast(list[object], value):
            yield from walk(child)


def validate() -> None:
    errors: list[str] = []
    items = read("items/items.json")
    codes: set[str] = set()
    for item in items:
        for code in item["codes"].split(","):
            code = code.strip()
            if code in codes:
                errors.append(f"Duplicate item code: {code}")
            codes.add(code)
    lua = (ROOT / "scripts/logic.lua").read_text()
    functions = set(re.findall(r"function\s+(\w+)\s*\(", lua))
    for code in re.findall(r'has\("([^\"]+)"\)', lua):
        if code not in codes:
            errors.append(f"Logic uses undefined item: {code}")
    maps = {m["name"] for m in read("maps/maps.json")}
    layouts: dict[str, Any] = {}
    for file in (ROOT / "layouts").glob("*.json"):
        data = read(file)
        layouts.update(data.get("layouts", data))
    for name, layout in layouts.items():
        for node in walk(layout):
            if node.get("type") == "layout" and node["key"] not in layouts:
                errors.append(f"{name}: undefined layout {node['key']}")
            if node.get("type") == "itemgrid":
                for row in node["rows"]:
                    for code in row:
                        if code not in codes:
                            errors.append(f"{name}: undefined grid item {code}")
            if node.get("type") == "map":
                for name_ in node.get("maps", []):
                    if name_ not in maps:
                        errors.append(f"{name}: undefined map {name_}")
    sections = 0
    for file in (ROOT / "locations").rglob("*.json"):
        for node in walk(read(file)):
            for marker in node.get("map_locations", []):
                if marker["map"] not in maps:
                    errors.append(f"{file.name}: undefined map {marker['map']}")
            if "access_rules" in node:
                sections += 1
                for rule in node["access_rules"]:
                    for token in rule.split(","):
                        token = token.strip()
                        known = functions if token.startswith("$") else codes
                        identifier = token[1:] if token.startswith("$") else token
                        if identifier not in known:
                            errors.append(f"{file.name}: undefined rule {token}")
    if errors:
        raise AssertionError("\n".join(errors))
    print(
        f"Validated {len(codes)} item codes, {len(functions)} Lua functions, "
        f"{sections} location rules, {len(maps)} maps, "
        f"and {len(layouts)} layouts."
    )


if __name__ == "__main__":
    validate()
