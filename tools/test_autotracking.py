"""Execute the actual tracker Lua callbacks using a small PopTracker API model."""

import argparse
from pathlib import Path
import sys
import unittest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lua-runtime", required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.lua_runtime.resolve()))
    from lupa import LuaRuntime

    class TrackingTests(unittest.TestCase):
        def setUp(self) -> None:
            self.lua = LuaRuntime(unpack_returned_tuples=True)
            self.lua.execute('''
                objects = {
                    hammer = {Type="toggle", Active=true},
                    pages = {Type="consumable", AcquiredCount=4, MaxCount=6},
                    ["@Stage/Check"] = {ChestCount=1, AvailableChestCount=0},
                }
                callbacks = {}
                Tracker = {BulkUpdate=false}
                function Tracker:FindObjectForCode(code) return objects[code] end
                Archipelago = {CheckedLocations={}}
                function Archipelago:AddClearHandler(name, callback) callbacks.clear = callback end
                function Archipelago:AddItemHandler(name, callback) callbacks.item = callback end
                function Archipelago:AddLocationHandler(name, callback) callbacks.location = callback end
                function clear_seed(hash)
                    callbacks.clear({format_version=1, catalog_hash=hash, tracker={
                        format_version=1, catalog_hash=hash,
                        items={["100"]={code="hammer",type="toggle"}, ["101"]={code="pages",type="consumable"}},
                        locations={["200"]="@Stage/Check"}
                    }})
                end
            ''')
            self.lua.execute((Path(__file__).resolve().parents[1] / "scripts/autotracking.lua").read_text(encoding="utf-8"))
            self.lua.globals().clear_seed("a" * 64)

        def test_check_does_not_grant_its_item(self) -> None:
            self.lua.execute('callbacks.location(200); assert(objects["@Stage/Check"].AvailableChestCount == 0); assert(not objects.hammer.Active)')

        def test_duplicate_packet_and_counter_limits(self) -> None:
            self.lua.execute('callbacks.item(0,101); callbacks.item(0,101); assert(objects.pages.AcquiredCount == 1); for i=1,10 do callbacks.item(i,101) end; assert(objects.pages.AcquiredCount == 6)')

        def test_reconnect_resets_then_replays_inventory_and_checks(self) -> None:
            self.lua.execute('callbacks.item(0,100); callbacks.location(200); assert(objects.hammer.Active)')
            self.lua.globals().clear_seed("a" * 64)
            self.lua.execute('assert(not objects.hammer.Active); assert(objects["@Stage/Check"].AvailableChestCount == 1); callbacks.item(0,100); assert(objects.hammer.Active); assert(not Tracker.BulkUpdate)')

        def test_wrong_catalog_and_unknown_ids_are_ignored(self) -> None:
            self.lua.execute('TRACKER_CATALOG_HASH = string.rep("b",64)')
            self.lua.globals().clear_seed("a" * 64)
            self.lua.execute('callbacks.item(0,100); callbacks.location(200); assert(not objects.hammer.Active); assert(objects["@Stage/Check"].AvailableChestCount == 1)')

        def test_cached_checks_are_restored_separately(self) -> None:
            self.lua.execute('Archipelago.CheckedLocations = {200}')
            self.lua.globals().clear_seed("a" * 64)
            self.lua.execute('assert(objects["@Stage/Check"].AvailableChestCount == 0); assert(not objects.hammer.Active)')

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TrackingTests))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
