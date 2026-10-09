"""Archipelago 0.6.8 adapter for the shared example definition.

This is the logic-example generation integration. Experimental native patches
and a protocol runtime exist separately; full gameplay integration is pending.
"""

from dataclasses import dataclass
import json
from pathlib import Path as FilePath
from typing import Callable, ClassVar

from BaseClasses import (  # pyright: ignore[reportMissingImports]
    CollectionState,
    Entrance,
    Item as APItem,
    ItemClassification,
    Location as APLocation,
    Region as APRegion,
)
from Options import PerGameCommonOptions  # pyright: ignore[reportMissingImports]
from worlds.AutoWorld import World  # pyright: ignore[reportMissingImports]

from ...data.example import example_game
from ...domain import EndGoal, Rules

GAME = example_game()
BASE_ID = 0x535300
FIXED_ITEMS = set(GAME.fixed_rewards.values())
ITEM_IDS = {item.name: BASE_ID + index for index, item in enumerate(GAME.items, 1) if item.id not in FIXED_ITEMS}
LOCATION_IDS = {loc.name: BASE_ID + index for index, loc in enumerate(GAME.locations, 1) if loc.id not in GAME.fixed_rewards}


@dataclass
class StickerStarOptions(PerGameCommonOptions):
    """Common AP options; game-specific options await verified game data."""


class StickerStarItem(APItem):
    game = "Paper Mario: Sticker Star (Logic Demo)"


class StickerStarLocation(APLocation):
    game = "Paper Mario: Sticker Star (Logic Demo)"


class StateInventory:
    def __init__(self, state: CollectionState, player: int, names: dict[str, str]) -> None:
        self.state = state
        self.player = player
        self.names = names

    def count(self, item_id: str) -> int:
        return self.state.count(self.names[item_id], self.player)


class SharedCatalogWorld(World):
    definition = GAME
    item_type: type[APItem] = StickerStarItem
    location_type: type[APLocation] = StickerStarLocation
    options_dataclass: ClassVar[type[PerGameCommonOptions]] = StickerStarOptions
    options: StickerStarOptions
    item_name_to_id = ITEM_IDS
    location_name_to_id = LOCATION_IDS
    origin_region_name = GAME.start.name
    topology_present = True
    required_client_version = (0, 6, 8)

    def create_item(self, name: str) -> APItem:
        item = next(item for item in self.definition.items if item.name == name)
        classification = (
            ItemClassification.progression
            if item.progression or item.id in set(self.definition.fixed_rewards.values())
            else ItemClassification.filler
        )
        return self.item_type(name, classification, self.item_name_to_id.get(name), self.player)

    def access_rule(self, rules: Rules) -> Callable[[CollectionState], bool]:
        names = {item.id: item.name for item in self.definition.items}
        return lambda state: rules.allows(StateInventory(state, self.player, names))

    def create_regions(self) -> None:
        regions = {region.id: APRegion(region.name, self.player, self.multiworld) for region in self.definition.regions}
        self.multiworld.regions.extend(regions.values())
        items = {item.id: item for item in self.definition.items}
        fixed = self.definition.fixed_rewards
        for loc in self.definition.locations:
            region = regions[loc.region_id]
            check = self.location_type(self.player, loc.name, self.location_name_to_id.get(loc.name), region)
            check.access_rule = self.access_rule(loc.rules)
            region.locations.append(check)
            if loc.id in fixed:
                check.place_locked_item(self.create_item(items[fixed[loc.id]].name))
        for path in self.definition.paths:
            for direction, vector in enumerate((path.forward, path.reverse)):
                source = regions[vector.source]
                entrance = Entrance(self.player, f"{path.id}:{direction}", source)
                entrance.access_rule = self.access_rule(vector.rules)
                source.exits.append(entrance)
                entrance.connect(regions[vector.target])
        end = next(loc for loc in self.definition.locations if isinstance(loc, EndGoal))
        self.multiworld.completion_condition[self.player] = lambda state: state.has(end.item.name, self.player)

    def create_items(self) -> None:
        items = {item.id: item for item in self.definition.items}
        self.multiworld.itempool.extend(self.create_item(items[item_id].name) for item_id in self.definition.pool)
        for item_id in self.definition.starting_items:
            self.multiworld.push_precollected(self.create_item(items[item_id].name))

    def fill_slot_data(self) -> dict[str, object]:
        return {"format_version": 1, "logic_demo": True, "playable_patch": False}

    def generate_output(self, output_directory: str) -> None:
        placements = {
            loc.id: {"item": item.name, "player": item.player}
            for loc in self.definition.locations
            if loc.id not in self.definition.fixed_rewards
            and (item := self.multiworld.get_location(loc.name, self.player).item) is not None
        }
        target = FilePath(output_directory) / f"{self.multiworld.get_out_file_name_base(self.player)}.stickerstar.json"
        target.write_text(
            json.dumps({"slot_data": self.fill_slot_data(), "placements": placements}, indent=2) + "\n",
            encoding="utf-8",
        )


class StickerStarWorld(SharedCatalogWorld):
    game = "Paper Mario: Sticker Star (Logic Demo)"
    item_name_to_id = ITEM_IDS
    location_name_to_id = LOCATION_IDS
