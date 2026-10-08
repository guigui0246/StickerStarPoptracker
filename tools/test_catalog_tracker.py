"""Execute generated tracker Lua against the shared graph's reachability oracle."""

import argparse
from collections import Counter
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.data.catalog import parse_catalog
from randomizer.integrations.archipelago.native_catalog import allocate_registry
from randomizer.integrations.archipelago.tracker_catalog import TrackerCatalog, lua_string
from randomizer.standalone.generation import InventoryState, reachable_regions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lua-runtime", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.lua_runtime.resolve()))
    from lupa import LuaRuntime
    game = parse_catalog({"format_version": 2,
        "items": [{"id": identifier, "name": identifier} for identifier in ("hammer", "paper", "coins", "victory")]
                 + [{"id": "key", "name": "key", "location": "event"}],
        "regions": [{"id": "menu", "name": "Menu", "starting": True}]
                   + [{"id": identifier, "name": identifier} for identifier in ("town", "cave", "island")],
        "locations": [{"id": identifier, "name": identifier, "region": region}
                      for identifier, region in (("a", "menu"), ("b", "menu"), ("c", "town"), ("d", "cave"), ("e", "island"))]
                     + [{"id": "event", "name": "Event", "region": "town", "requires": {"count": ["coins", 2]}},
                        {"id": "goal", "name": "Goal", "region": "cave", "type": "end_goal", "item": "victory"}],
        "paths": [{"id": "town", "forward": {"source": "menu", "target": "town", "requires": {"item": "hammer"}},
                   "reverse": {"source": "town", "target": "menu", "requires": {"item": "paper"}}},
                  {"id": "cave", "forward": {"source": "town", "target": "cave", "requires": {"item": "key"}},
                   "reverse": {"source": "cave", "target": "town"}},
                  {"id": "island", "forward": {"source": "menu", "target": "island", "requires": {
                       "any": [{"count": ["hammer", 2]}, {"all": [{"item": "paper"}, {"count": ["coins", 2]}]}]}},
                   "reverse": {"source": "island", "target": "menu", "requires": {"any": []}}}],
        "pool": ["hammer", "hammer", "coins", "coins", "paper"]})
    tracker = TrackerCatalog(game, allocate_registry(game), "a" * 64)
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute('providers = {}; Tracker = {}; function Tracker:ProviderCountForCode(code) return providers[code] or 0 end')
    lua.execute(tracker.lua())
    # Escapes must be valid Lua, including embedded controls and UTF-8.
    for value in ('quote"\\', "control\x01\n9", "é_日本"):
        assert lua.eval(lua_string(value)) == value
    scenarios = 0
    for hammer, paper, coins in product(range(3), range(2), range(3)):
        state = InventoryState(Counter({"hammer": hammer, "paper": paper, "coins": coins}))
        providers = lua.globals().providers
        for identifier, count in state.items.items():
            providers[tracker.item_code(identifier)] = count
        events: set[str] = set()
        while True:
            regions = reachable_regions(game, state)
            available = [location for location in game.locations if location.id in game.fixed_rewards
                         and location.id not in events and location.region_id in regions and location.rules.allows(state)]
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


if __name__ == "__main__":
    main()
