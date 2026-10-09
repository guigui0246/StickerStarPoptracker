"""Generate tracker predicates from the shared typed graph, including events."""

from collections import Counter
from dataclasses import dataclass

from ...domain import GameDefinition, Rules
from .native_catalog import NativeAPRegistry


def lua_string(value: str) -> str:
    # Lua accepts UTF-8 literals; JSON's control-character \u escapes are invalid.
    return (
        '"'
        + "".join(
            (
                "\\" + character
                if character in ('"', "\\")
                else f"\\{ord(character):03d}"
                if ord(character) < 32 or ord(character) == 127
                else character
            )
            for character in value
        )
        + '"'
    )


def expression(rule: Rules) -> str:
    if rule.operator == "item":
        return f"(counts[{lua_string(rule.item_id)}] >= {rule.amount})"
    children = [expression(child) for child in rule.children]
    if not children:
        return "true" if rule.operator == "all" else "false"
    return "(" + (" and " if rule.operator == "all" else " or ").join(children) + ")"


@dataclass(frozen=True)
class TrackerCatalog:
    game: GameDefinition
    registry: NativeAPRegistry
    catalog_hash: str

    def __post_init__(self) -> None:
        self.registry.validate(self.game)
        if len(self.catalog_hash) != 64 or any(character not in "0123456789abcdef" for character in self.catalog_hash):
            raise ValueError("Tracker requires a catalog SHA-256")

    def item_code(self, identifier: str) -> str:
        return f"ss_item_{self.registry.items[identifier]}"

    def location_code(self, identifier: str) -> str:
        return f"@ss_location_{self.registry.locations[identifier]}/Check"

    def access_function(self, identifier: str) -> str:
        return f"SS_ACCESS_{self.registry.locations[identifier]}"

    def mappings(self) -> dict[str, object]:
        fixed = self.game.fixed_rewards
        return {
            "format_version": 1,
            "catalog_hash": self.catalog_hash,
            "items": {
                str(self.registry.items[item.id]): {"code": self.item_code(item.id), "type": "consumable"}
                for item in self.game.items
                if item.id not in set(fixed.values())
            },
            "locations": {
                str(self.registry.locations[location.id]): self.location_code(location.id)
                for location in self.game.locations
                if location.id not in fixed
            },
        }

    def lua(self) -> str:
        fixed = self.game.fixed_rewards
        starters = Counter(self.game.starting_items)
        lines = [
            "-- Generated from the shared typed catalog; do not edit predicates here.",
            f"TRACKER_CATALOG_HASH = {lua_string(self.catalog_hash)}",
            "local function ss_reachability()",
            "  local counts, reached, events = {}, {}, {}",
        ]
        for item in self.game.items:
            value = (
                "0"
                if item.id in set(fixed.values())
                else (f"math.max({starters[item.id]}, Tracker:ProviderCountForCode({lua_string(self.item_code(item.id))}))")
            )
            lines.append(f"  counts[{lua_string(item.id)}] = {value}")
        lines += [
            f"  reached[{lua_string(self.game.start.id)}] = true",
            "  local changed = true",
            "  while changed do",
            "    changed = false",
        ]
        for path in self.game.paths:
            for vector in (path.forward, path.reverse):
                source, target = lua_string(vector.source), lua_string(vector.target)
                lines += [
                    f"    if reached[{source}] and not reached[{target}] and {expression(vector.rules)} then",
                    f"      reached[{target}], changed = true, true",
                    "    end",
                ]
        for location in self.game.locations:
            if location.id not in fixed:
                continue
            key, region, reward = lua_string(location.id), lua_string(location.region_id), lua_string(fixed[location.id])
            lines += [
                f"    if not events[{key}] and reached[{region}] and {expression(location.rules)} then",
                f"      counts[{reward}] = counts[{reward}] + 1",
                f"      events[{key}], changed = true, true",
                "    end",
            ]
        lines += ["  end", "  return reached, counts", "end"]
        for location in self.game.locations:
            if location.id not in fixed:
                lines += [
                    f"function {self.access_function(location.id)}()",
                    "  local reached, counts = ss_reachability()",
                    f"  return reached[{lua_string(location.region_id)}] == true and {expression(location.rules)}",
                    "end",
                ]
        return "\n".join(lines) + "\n"

    def data_package(self) -> dict[str, object]:
        fixed = self.game.fixed_rewards
        return {
            "catalog_hash": self.catalog_hash,
            "items": {
                item.name: self.registry.items[item.id] for item in self.game.items if item.id not in set(fixed.values())
            },
            "locations": {
                location.name: self.registry.locations[location.id]
                for location in self.game.locations
                if location.id not in fixed
            },
            "tracker": self.mappings(),
        }

    def definitions(self) -> dict[str, object]:
        """Pack authors can load these item/location definitions with the Lua."""
        fixed = self.game.fixed_rewards
        return {
            "format_version": 1,
            "catalog_hash": self.catalog_hash,
            "tracker": self.mappings(),
            "items": [
                {"name": item.name, "type": "consumable", "codes": self.item_code(item.id), "max_quantity": 9999}
                for item in self.game.items
                if item.id not in set(fixed.values())
            ],
            "locations": [
                {
                    "name": f"ss_location_{self.registry.locations[location.id]}",
                    "sections": [
                        {"name": "Check", "item_count": 1, "access_rules": ["$" + self.access_function(location.id)]}
                    ],
                    "display_name": location.name,
                }
                for location in self.game.locations
                if location.id not in fixed
            ],
        }
