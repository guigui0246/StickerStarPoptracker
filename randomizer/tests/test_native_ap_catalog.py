from typing import Any, cast
from copy import deepcopy
import unittest

from ..data.catalog import parse_catalog
from ..integrations.archipelago.native_catalog import ITEM_BASE, NativeAPCatalog, NativeAPRegistry, allocate_registry
from ..integrations.rom.native_generation import catalog_digest


def fixture() -> tuple[dict, dict]:
    """Artificial access rules, real source IDs: generation test only."""
    catalog = {
        "format_version": 2,
        "items": [
            {"id": "hammer", "name": "Hammer"},
            {"id": "paper", "name": "Paperization"},
            {"id": "town", "name": "Decalburg Access"},
            {"id": "coins", "name": "25 Coins", "progression": False},
            {"id": "page", "name": "Album Page"},
            {"id": "victory", "name": "Victory"},
        ],
        "regions": [{"id": "menu", "name": "Menu", "starting": True}, {"id": "town", "name": "Decalburg"}],
        "locations": (
            [{"id": f"star{index}", "name": f"Fixture star {index}", "region": "menu"} for index in range(3)]
            + [
                {"id": f"museum{index}", "name": f"Fixture exhibit {index}", "region": "town", "requires": {"item": "hammer"}}
                for index in range(6)
            ]
            + [
                {"id": "banner", "name": "Fixture banner", "region": "menu"},
                {
                    "id": "end",
                    "name": "Fixture victory",
                    "region": "town",
                    "type": "end_goal",
                    "item": "victory",
                    "requires": {"all": [{"item": "hammer"}, {"item": "paper"}]},
                },
            ]
        ),
        "paths": [
            {
                "id": "town",
                "forward": {"source": "menu", "target": "town", "requires": {"item": "town"}},
                "reverse": {"source": "town", "target": "menu"},
            }
        ],
        "pool": ["hammer", "paper", "town"] + ["coins"] * 7,
    }
    stars = (("hei_2_01", "GF_WM_A03_A04"), ("hei_2_03", "GF_WM_A03_A05"), ("hei_3_05", "GF_WM_A02_A03"))
    bindings = {
        "format_version": 1,
        "catalog_sha256": catalog_digest(catalog),
        "items": {
            "hammer": {"kind": "ability", "value": "hammer"},
            "paper": {"kind": "ability", "value": "paperization"},
            "town": {"kind": "stage_access", "value": "X00"},
            "coins": {"kind": "coins", "value": 25},
            "page": {"kind": "page", "value": 1},
            "victory": {"kind": "victory", "value": 1},
        },
        "locations": (
            [
                {"location": f"star{index}", "source": {"map_name": name, "source_flag": flag}}
                for index, (name, flag) in enumerate(stars)
            ]
            + [
                {
                    "location": f"museum{index}",
                    "source": {"category": "museum", "source_flag": f"gf_museum_battle_seal_{index + 1:03d}"},
                }
                for index in range(6)
            ]
            + [
                {"location": "banner", "source": {"honor": "battle_excellent", "mode": "original"}},
                {
                    "location": "end",
                    "source": {
                        "category": "victory",
                        "script_file": "Script/Map/W6_BOS/w6_bos_04.bin",
                        "function": "koopa_battle_after_event_init",
                    },
                },
            ]
        ),
    }
    return catalog, bindings


class NativeAPCatalogTests(unittest.TestCase):
    def test_registry_preserves_ids_and_never_recycles_retired_entries(self) -> None:
        catalog, _ = fixture()
        game = parse_catalog(catalog)
        original = allocate_registry(game)
        retired = NativeAPRegistry(original.items | {"retired": max(original.items.values()) + 1}, original.locations)
        changed = deepcopy(catalog)
        changed["items"].append({"id": "new_filler", "name": "New filler", "progression": False})
        extended = allocate_registry(parse_catalog(changed), retired)
        self.assertEqual({key: extended.items[key] for key in original.items}, original.items)
        self.assertGreater(extended.items["new_filler"], extended.items["retired"])
        self.assertEqual(NativeAPRegistry.parse(extended.encode()), extended)

    def test_bundle_binds_catalog_sources_ids_and_target_rom(self) -> None:
        catalog, bindings = fixture()
        registry = allocate_registry(parse_catalog(catalog))
        data = {
            "format_version": 1,
            "catalog": catalog,
            "bindings": bindings,
            "registry": registry.encode(),
            "rom_sha256": "a" * 64,
            "sticker_policy": None,
        }
        bundle = NativeAPCatalog.parse(data)
        self.assertEqual(bundle.game, parse_catalog(catalog))
        self.assertEqual(bundle.catalog_hash, catalog_digest(data))
        changed = deepcopy(data)
        changed["catalog"]["pool"][0] = "coins"
        with self.assertRaises(ValueError):
            NativeAPCatalog.parse(changed)
        for registry in (NativeAPRegistry({}, {}),):
            with self.assertRaises(ValueError):
                registry.validate(bundle.game)

    def test_invalid_ids_and_sticker_catalog_without_policy_fail(self) -> None:
        for identifiers in ({"one": ITEM_BASE, "two": ITEM_BASE}, {"one": True}, {"one": 1}):
            with self.assertRaises(ValueError):
                NativeAPRegistry(cast(Any, identifiers), {})
        catalog, bindings = fixture()
        bindings["items"]["coins"] = {"kind": "sticker_copy", "value": "SL_JUMP"}
        data = {
            "format_version": 1,
            "catalog": catalog,
            "bindings": bindings,
            "registry": allocate_registry(parse_catalog(catalog)).encode(),
            "rom_sha256": "a" * 64,
            "sticker_policy": None,
        }
        with self.assertRaises(ValueError):
            NativeAPCatalog.parse(data)
