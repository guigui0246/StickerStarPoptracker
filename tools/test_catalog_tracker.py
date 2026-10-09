"""Execute generated tracker Lua against the shared graph's reachability oracle."""

from typing import Any, cast

import argparse
from collections import Counter
from dataclasses import replace
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.data.catalog import parse_catalog
from randomizer.integrations.archipelago.native_catalog import allocate_registry
from randomizer.integrations.archipelago.tracker_catalog import TrackerCatalog, lua_string
from randomizer.integrations.archipelago.tracker_pack import pack_files
from randomizer.standalone.generation import InventoryState, reachable_regions
from randomizer.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lua-runtime", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.lua_runtime.resolve()))
    from lupa import LuaRuntime  # pyright: ignore[reportMissingModuleSource]

    game = parse_catalog(
        cast(
            Any,
            {
                "format_version": 2,
                "items": [{"id": identifier, "name": identifier} for identifier in ("hammer", "paper", "coins", "victory")]
                + [{"id": "key", "name": "key", "location": "event"}],
                "regions": [{"id": "menu", "name": "Menu", "starting": True}]
                + [{"id": identifier, "name": identifier} for identifier in ("town", "cave", "island")],
                "locations": [
                    {"id": identifier, "name": identifier, "region": region}
                    for identifier, region in (("a", "menu"), ("b", "menu"), ("c", "town"), ("d", "cave"), ("e", "island"))
                ]
                + [
                    {"id": "event", "name": "Event", "region": "town", "requires": {"count": ["coins", 2]}},
                    {"id": "goal", "name": "Goal", "region": "cave", "type": "end_goal", "item": "victory"},
                ],
                "paths": [
                    {
                        "id": "town",
                        "forward": {"source": "menu", "target": "town", "requires": {"item": "hammer"}},
                        "reverse": {"source": "town", "target": "menu", "requires": {"item": "paper"}},
                    },
                    {
                        "id": "cave",
                        "forward": {"source": "town", "target": "cave", "requires": {"item": "key"}},
                        "reverse": {"source": "cave", "target": "town"},
                    },
                    {
                        "id": "island",
                        "forward": {
                            "source": "menu",
                            "target": "island",
                            "requires": {
                                "any": [{"count": ["hammer", 2]}, {"all": [{"item": "paper"}, {"count": ["coins", 2]}]}]
                            },
                        },
                        "reverse": {"source": "island", "target": "menu", "requires": {"any": []}},
                    },
                ],
                "pool": ["hammer", "hammer", "coins", "coins", "paper"],
            },
        )
    )
    tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64)
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute("providers = {}; Tracker = {}; function Tracker:ProviderCountForCode(code) return providers[code] or 0 end")
    lua.execute(tracker.lua())
    # Escapes must be valid Lua, including embedded controls and UTF-8.
    for value in ('quote"\\', "control\x01\n9", "é_日本"):
        assert lua.eval(lua_string(value)) == value
    scenarios = 0
    for hammer, paper, coins in product(range(3), range(2), range(3)):
        state = InventoryState(Counter({"hammer": hammer, "paper": paper, "coins": coins}))
        providers = cast(Any, lua.globals()).providers
        for identifier, count in state.items.items():
            providers[tracker.item_code(identifier)] = count
        events: set[str] = set()
        while True:
            regions = reachable_regions(game, state)
            available = [
                location
                for location in game.locations
                if location.id in game.fixed_rewards
                and location.id not in events
                and location.region_id in regions
                and location.rules.allows(state)
            ]
            if not available:
                break
            for location in available:
                events.add(location.id)
                state.items[game.fixed_rewards[location.id]] += 1
        regions = reachable_regions(game, state)
        for location in game.locations:
            if location.id in game.fixed_rewards:
                continue
            actual = lua.globals()[tracker.access_function(location.id)]()
            expected = location.region_id in regions and location.rules.allows(state)
            assert actual == expected, (hammer, paper, coins, location.id, actual, expected)
        scenarios += 1
    print(f"Generated tracker Lua matches the shared graph in {scenarios} inventory scenarios.")
    lua.execute("""
        objects, callbacks = {}, {}
        function Tracker:FindObjectForCode(code) return objects[code] end
        Archipelago = {CheckedLocations={}}
        function Archipelago:AddClearHandler(name, callback) callbacks.clear = callback end
        function Archipelago:AddItemHandler(name, callback) callbacks.item = callback end
        function Archipelago:AddLocationHandler(name, callback) callbacks.location = callback end
    """)
    for item in game.items:
        if item.id not in set(game.fixed_rewards.values()):
            lua.execute(f"objects[{lua_string(tracker.item_code(item.id))}] = {{AcquiredCount=0, MaxCount=9999}}")
    for location in game.locations:
        if location.id not in game.fixed_rewards:
            code = lua_string(tracker.location_code(location.id))
            lua.execute(f"objects[{code}] = {{ChestCount=1, AvailableChestCount=1}}")
    files = pack_files(tracker)
    lua.execute(files["scripts/autotracking.lua"])
    mappings = cast(Any, tracker.mappings())
    slot = lua.table_from({
        "catalog_hash": tracker.catalog_hash,
        "tracker": lua.table_from(mappings, recursive=True),
    })
    callbacks = cast(Any, lua.globals()).callbacks
    objects = cast(Any, lua.globals()).objects
    callbacks.clear(slot)
    hammer_id = tracker.registry.items["hammer"]
    marker_id = tracker.registry.locations["a"]
    callbacks.location(marker_id)
    assert objects[tracker.location_code("a")].AvailableChestCount == 0
    assert objects[tracker.item_code("hammer")].AcquiredCount == 0
    callbacks.item(0, hammer_id)
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 1
    callbacks.item(1, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 2
    callbacks.clear(slot)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 0
    assert objects[tracker.location_code("a")].AvailableChestCount == 1
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 1
    slot["catalog_hash"] = "b" * 64
    callbacks.clear(slot)
    callbacks.item(0, hammer_id)
    callbacks.location(marker_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 0
    assert objects[tracker.location_code("a")].AvailableChestCount == 1
    slot["catalog_hash"] = tracker.catalog_hash
    slot["tracker"]["items"][str(hammer_id)]["code"] = "wrong_registry"
    callbacks.clear(slot)
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 0
    slot["tracker"]["items"][str(hammer_id)]["code"] = tracker.item_code("hammer")
    precollected = TrackerCatalog(replace(game, starting_items=("hammer",)), tracker.registry, tracker.catalog_hash)
    lua.execute(precollected.lua())
    lua.execute(pack_files(precollected)["scripts/autotracking.lua"])
    callbacks.clear(slot)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 1
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 1
    callbacks.item(1, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 2
    configured = TrackerCatalog(game, tracker.registry, tracker.catalog_hash, Settings())
    slot["tracker"] = lua.table_from(cast(Any, configured.mappings()), recursive=True)
    lua.execute(configured.lua())
    lua.execute(pack_files(configured)["scripts/autotracking.lua"])
    callbacks.clear(slot)
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 1
    slot["tracker"]["settings"]["album_pages"] = "randomized"
    callbacks.clear(slot)
    callbacks.item(0, hammer_id)
    assert objects[tracker.item_code("hammer")].AcquiredCount == 0
    print(
        "Generated pack callbacks pass separation, replay, reconnect, catalog/registry/settings mismatch and starting echoes."
    )


if __name__ == "__main__":
    main()
