from copy import deepcopy
from typing import Any
import unittest
from unittest.mock import Mock

from ..integrations.rom.native_delivery import FlagReward, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import checks
from ..integrations.rom.production_sources import ProductionSources, needs_source, reward_id
from ..integrations.rom.ksm import KsmDocument, KsmImport, KsmVariable, KsmValueType
from .test_native_ap_catalog import fixture


class ProductionSourceTests(unittest.TestCase):
    def test_metadata_filter_keeps_every_hook_family_and_rejects_patched_inputs(self) -> None:
        empty = Mock(spec=KsmDocument, statics=(), constants=(), globals=(), imports=())
        self.assertFalse(needs_source("Script/Map/HEI/hei_5_00.bin", empty))
        for filename in (
            "Script/Map/HEI/hei_2_04.bin", "Script/Map/W4_KAW/w4_kaw_00.bin",
            "Script/Map/MAC/mac_1_00.bin", "Script/Map/HEI/hei_2_01.bin",
        ):
            self.assertTrue(needs_source(filename, empty))
        empty.imports = (KsmImport(1, "mobj_goal_block_exit", 8, 1, None),)
        self.assertTrue(needs_source("Script/Map/HEI/hei_5_00.bin", empty))
        empty.imports = (KsmImport(1, "item_static_entry", 8, 1, None),)
        self.assertFalse(needs_source("Script/Map/HEI/hei_5_00.bin", empty))
        empty.constants = (KsmVariable(1, None, KsmValueType.STRING, 3, "PK_FIELD_BRIDGE", 0),)
        self.assertTrue(needs_source("Script/Map/HEI/hei_5_00.bin", empty))
        empty.imports = (KsmImport(1, "rando_deliver", 8, 1, None),)
        with self.assertRaisesRegex(ValueError, "original scripts"):
            needs_source("Script/Map/HEI/hei_5_00.bin", empty)
        empty.imports = ()
        empty.statics = (KsmVariable(1, "gf_rando_check_0000", KsmValueType.BOOLEAN, 7, False, 0),)
        with self.assertRaisesRegex(ValueError, "original scripts"):
            needs_source("Script/Map/HEI/hei_5_00.bin", empty)

    def setUp(self) -> None:
        catalog, bindings = fixture()
        rewards = {
            identifier: NativeReward(NativeRewardKind(raw["kind"]), raw["value"])
            for identifier, raw in bindings["items"].items()
        }
        identifiers = {identifier: reward_id(native) for identifier, native in rewards.items()}
        sources = checks([{**row["source"], "reward": {"kind": "coins", "value": 25}} for row in bindings["locations"]])
        identifiers.update({row["location"]: source.id for row, source in zip(bindings["locations"], sources, strict=True)})

        def rename(value: Any) -> Any:
            if isinstance(value, str):
                return identifiers.get(value, value)
            if isinstance(value, list):
                return [rename(child) for child in value]
            if isinstance(value, dict):
                return {key: rename(child) for key, child in value.items()}
            return value

        self.catalog = rename(catalog)
        self.sources = ProductionSources(sources, tuple(rewards.values()), frozenset({"gf_story_done"}), {})

    def test_exact_source_inventory_binds_to_shared_catalog(self) -> None:
        result = self.sources.bind(self.catalog)
        self.assertEqual(set(result.locations), {check.id for check in self.sources.checks})
        self.assertIsNotNone(result.catalog_hash)
        self.assertEqual(result.items["ability/hammer"].kind, NativeRewardKind.ABILITY)

    def test_missing_checks_and_unobserved_rewards_are_rejected(self) -> None:
        data = deepcopy(self.catalog)
        data["locations"].pop(0)
        data["pool"].pop()
        with self.assertRaisesRegex(ValueError, "every observed check"):
            self.sources.bind(data)
        data = deepcopy(self.catalog)
        data["items"].append({"id": "item/PK_UNKNOWN", "name": "Unobserved"})
        with self.assertRaisesRegex(ValueError, "observed kind/value"):
            self.sources.bind(data)

    def test_fixed_story_observations_cannot_replace_a_shuffled_check(self) -> None:
        data = deepcopy(self.catalog)
        data["items"].append({"id": "event/gf_story_done", "name": "Story", "location": "story"})
        data["locations"].append({"id": "story", "name": "Story check", "region": data["regions"][1]["id"]})
        result = self.sources.bind(data)
        source = result.locations["story"]
        self.assertIsInstance(source, FlagReward)
        self.assertEqual(source.reward.kind, NativeRewardKind.EVENT)
        data["items"][-1]["id"] = "event/gf_unknown"
        with self.assertRaisesRegex(ValueError, "original, separate story flag"):
            self.sources.bind(data)
