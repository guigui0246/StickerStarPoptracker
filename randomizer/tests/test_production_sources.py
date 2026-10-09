from copy import deepcopy
from typing import Any
import unittest

from ..integrations.rom.native_delivery import FlagReward, NativeReward, NativeRewardKind
from ..integrations.rom.plan_io import checks
from ..integrations.rom.production_sources import ProductionSources, reward_id
from .test_native_ap_catalog import fixture


class ProductionSourceTests(unittest.TestCase):
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
