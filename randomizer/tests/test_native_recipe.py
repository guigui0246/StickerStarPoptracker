import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ..integrations.rom.native_delivery import DeliveryPlan, FlagReward, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.native_recipe import NativeRecipe, apply_native_recipe, create_native_recipe, decode_native_recipe
from ..integrations.rom.plan_io import decode_plan, encode_plan
from ..integrations.rom.seed_patch import canonical, digest


class NativeRecipeTests(unittest.TestCase):
    plan = DeliveryPlan((GoalBlockReward("map", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 20)),
                         FlagReward("museum", "gf_donation", NativeReward(NativeRewardKind.ITEM, "SL_FAN"))))

    def test_roundtrip_contains_only_recipe_not_rom_assets(self) -> None:
        recipe = NativeRecipe("seed-one", "a" * 64, self.plan)
        encoded = recipe.encode()
        self.assertEqual(decode_native_recipe(encoded), recipe)
        self.assertEqual(decode_plan(encode_plan(self.plan)), self.plan)
        self.assertEqual(encoded, recipe.encode())
        self.assertNotIn(b"KSMR", encoded)
        self.assertNotIn(b"KDMR", encoded)

    def test_identical_placements_with_different_seed_names_have_distinct_save_identity(self):
        first = NativeRecipe("seed-one", "a" * 64, self.plan)
        second = NativeRecipe("seed-two", "a" * 64, self.plan)
        self.assertNotEqual(first.plan.fingerprint, second.plan.fingerprint)
        self.assertIsNone(self.plan.seed_name)
        with self.assertRaises(ValueError):
            NativeRecipe("seed-two", "a" * 64, first.plan)

    def test_strict_fields_types_versions_and_save_fingerprint(self) -> None:
        original = json.loads(NativeRecipe("seed", "a" * 64, self.plan).encode())
        changes = [("format_version", True), ("algorithm", "unknown"), ("rom_sha256", "BAD"), ("save_seed_fingerprint", "0" * 32), ("extra", "field")]
        for key, value in changes:
            payload = dict(original)
            payload[key] = value
            payload.pop("recipe_sha256")
            payload["recipe_sha256"] = digest(canonical(payload))
            with self.assertRaises(ValueError):
                decode_native_recipe(canonical(payload))
        malformed = encode_plan(self.plan)
        malformed["checks"][0]["reward"]["value"] = True
        with self.assertRaises(ValueError):
            decode_plan(malformed)
        with self.assertRaises(ValueError):
            decode_native_recipe(b'{"format_version":2,"format_version":2}')

    def test_wrong_rom_and_existing_output_fail_before_native_build(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rom = root / "game.3ds"
            rom.write_bytes(b"synthetic game source")
            project = Mock(source=rom)
            recipe = create_native_recipe(project, "seed", self.plan)
            output = root / "mod"
            with patch("randomizer.integrations.rom.native_recipe.build_reward_mod") as build:
                rom.write_bytes(b"different source")
                with self.assertRaises(ValueError):
                    apply_native_recipe(project, recipe, output, root / "compiler.py")
                build.assert_not_called()
                output.mkdir()
                with self.assertRaises(FileExistsError):
                    apply_native_recipe(project, recipe, output, root / "compiler.py")


if __name__ == "__main__":
    unittest.main()
