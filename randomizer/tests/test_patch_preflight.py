"""Invalid companion outputs must fail before writing a native seed recipe."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from ..integrations.rom.native_generation import NativeBindings
from ..patch import main
from .test_native_ap_catalog import fixture


class PatchPreflightTests(unittest.TestCase):
    def run_preflight(self, directory: Path, suffix: str, content: str) -> None:
        data, raw_bindings = fixture()
        bindings = NativeBindings.parse(raw_bindings, data)
        output = directory / "seed.stickerpatch"
        existing = Path(str(output) + suffix)
        existing.write_text(content, encoding="utf-8")
        recipe = Mock()
        arguments = [
            "patch", "generate-native-catalog", "unused.3ds", "--catalog", "unused.json",
            "--bindings", "unused-bindings.json", "--seed", "preflight", "--output", str(output),
        ]
        with (
            patch.object(sys, "argv", arguments),
            patch("randomizer.patch.RomProject"),
            patch("randomizer.patch.load_catalog_data", return_value=data),
            patch("randomizer.patch.NativeBindings.load", return_value=bindings),
            patch("randomizer.patch.create_native_recipe", return_value=recipe),
            redirect_stderr(StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main()
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(output.exists())
        self.assertEqual(existing.read_text(encoding="utf-8"), content)
        recipe.encode.assert_not_called()

    def test_invalid_registry_does_not_leave_an_orphaned_recipe(self) -> None:
        with TemporaryDirectory() as directory:
            self.run_preflight(Path(directory), ".registry.json", "{}")

    def test_existing_tracker_pack_is_preserved_without_writing_recipe(self) -> None:
        with TemporaryDirectory() as directory:
            self.run_preflight(Path(directory), ".tracker.zip", "existing pack sentinel")
