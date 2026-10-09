"""Verify installable ZIP layout without recompiling the game in unit tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
import zipfile

from ..integrations.rom.mod_archive import build_mod_archive
from ..integrations.rom.native_delivery import DeliveryPlan, GoalBlockReward, NativeReward, NativeRewardKind
from ..integrations.rom.project import RomProject
from ..integrations.rom.native_recipe import NativeRecipe


class ModArchiveTests(unittest.TestCase):
    def test_title_tree_and_reports_are_separate_and_existing_output_is_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            mod = root / "source"
            for name in ("romfs/Data/test.bin", "exefs/code.ips", "exefs/code.S", "patch-report.json"):
                path = mod / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")
            plan = DeliveryPlan((GoalBlockReward("map", "GF_WM_A01_A02", NativeReward(NativeRewardKind.COINS, 25)),))
            recipe = NativeRecipe("test", "a" * 64, plan)
            output = root / "seed.zip"
            with patch("randomizer.integrations.rom.mod_archive.apply_native_recipe", return_value=mod):
                build_mod_archive(Mock(spec=RomProject), recipe, output, root / "compiler")
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(set(archive.namelist()), {
                        "00040000000A5F00/romfs/Data/test.bin", "00040000000A5F00/exefs/code.ips",
                        "reports/exefs/code.S", "reports/patch-report.json",
                    })
                original = output.read_bytes()
                with self.assertRaises(FileExistsError):
                    build_mod_archive(Mock(spec=RomProject), recipe, output, root / "compiler")
                self.assertEqual(original, output.read_bytes())
