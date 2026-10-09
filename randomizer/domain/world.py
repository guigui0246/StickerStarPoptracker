"""Validated game definition independent of ROMs and Archipelago."""

from dataclasses import dataclass
from .items import Event, Item
from .locations import EndGoal, Goal, Location
from .regions import Path, Region, StartingRegion


@dataclass(frozen=True)
class GameDefinition:
    items: tuple[Item, ...]
    regions: tuple[Region, ...]
    locations: tuple[Location, ...]
    paths: tuple[Path, ...]
    pool: tuple[str, ...]
    starting_items: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for objects in (self.items, self.regions, self.locations, self.paths):
            ids = [obj.id for obj in objects]
            if any(not value for value in ids) or len(ids) != len(set(ids)):
                raise ValueError("IDs must be nonempty and unique within each category")
        if len({item.name for item in self.items}) != len(self.items):
            raise ValueError("Item names must be unique")
        if len({loc.name for loc in self.locations}) != len(self.locations):
            raise ValueError("Location names must be unique")
        if len({region.name for region in self.regions}) != len(self.regions):
            raise ValueError("Region names must be unique")
        if sum(isinstance(region, StartingRegion) for region in self.regions) != 1:
            raise ValueError("Exactly one StartingRegion is required")
        if sum(isinstance(loc, EndGoal) for loc in self.locations) != 1:
            raise ValueError("Exactly one EndGoal is required")
        items = {item.id: item for item in self.items}
        regions = {region.id for region in self.regions}
        locations = {loc.id: loc for loc in self.locations}
        fixed: dict[str, str] = {}
        for loc in self.locations:
            if loc.region_id not in regions:
                raise ValueError(f"Unknown region at {loc.id}")
            if isinstance(loc, Goal):
                if items.get(loc.item.id) != loc.item:
                    raise ValueError("Goal reward must be in the item registry")
                fixed[loc.id] = loc.item.id
        for item in self.items:
            if isinstance(item, Event):
                if item.location_id not in locations:
                    raise ValueError("Event must reference an existing location")
                if item.location_id in fixed and fixed[item.location_id] != item.id:
                    raise ValueError("Conflicting fixed rewards")
                fixed[item.location_id] = item.id
        fixed_items = set(fixed.values())
        if fixed_items.intersection(self.pool + self.starting_items):
            raise ValueError("Fixed rewards cannot be shuffled or precollected")
        if set(self.pool + self.starting_items) - items.keys():
            raise ValueError("Unknown pool or starting item")
        if len(self.pool) != len(self.locations) - len(fixed):
            raise ValueError("Pool must contain one reward per randomized location")
        rules = [loc.rules for loc in self.locations]
        for path in self.paths:
            for vector in (path.forward, path.reverse):
                if {vector.source, vector.target} - regions:
                    raise ValueError("Unknown path endpoint")
                rules.append(vector.rules)
        available = set(self.pool + self.starting_items) | fixed_items
        for rule in rules:
            if rule.referenced_items() - available:
                raise ValueError("Rule references an unavailable item")

    @property
    def start(self) -> StartingRegion:
        return next(region for region in self.regions if isinstance(region, StartingRegion))

    @property
    def fixed_rewards(self) -> dict[str, str]:
        result = {loc.id: loc.item.id for loc in self.locations if isinstance(loc, Goal)}
        result.update({item.location_id: item.id for item in self.items if isinstance(item, Event)})
        return result
