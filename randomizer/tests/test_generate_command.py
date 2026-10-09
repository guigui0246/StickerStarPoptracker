"""Verify the user-facing command drives both native generation and application."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from ..standalone.__main__ import bundled_compiler, copy_patch_report, main, output_paths


class GenerateCommandTests(unittest.TestCase):
    def test_random_seed_and_automatic_output_run_both_steps(self) -> None:
        with patch("randomizer.standalone.__main__.secrets.randbits", return_value=123), \
                patch("randomizer.patch.main") as native, \
                patch("randomizer.standalone.__main__.copy_patch_report"), redirect_stdout(StringIO()):
            main(["--logic", "no-logic", "game.3ds"])
        generation, application = [call.args[0] for call in native.call_args_list]
        self.assertEqual(generation[0], "generate-no-logic")
        self.assertIn("--open-ground-routes", generation)
        self.assertEqual(generation[generation.index("--seed") + 1], "123")
        self.assertEqual(Path(generation[generation.index("--output") + 1]),
                         Path("generated/sticker-star-123/seed.stickerpatch"))
        self.assertEqual(generation[generation.index("--compiler") + 1], str(bundled_compiler()))
        self.assertEqual(application[0], "apply")
        self.assertEqual(Path(application[-1]), Path("generated/sticker-star-123/mod.zip"))

    def test_explicit_rom_seed_settings_and_zip_are_forwarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "custom.zip"
            with patch("randomizer.patch.main") as native, \
                    patch("randomizer.standalone.__main__.copy_patch_report"), redirect_stdout(StringIO()):
                main(["--rom", "game.3ds", "--seed", "abc", "--output", str(output),
                      "--museum", "off", "--starting-level", "random", "--start-with", "ability/hammer"])
            generation, application = [call.args[0] for call in native.call_args_list]
            self.assertEqual(generation[generation.index("--museum") + 1], "off")
            self.assertEqual(generation[generation.index("--starting-level") + 1], "random")
            self.assertEqual(generation[generation.index("--start-with") + 1], "ability/hammer")
            self.assertEqual(Path(application[1]), output.with_suffix(".stickerpatch"))
            self.assertEqual(application[-1], str(output))

    def test_vanilla_map_can_be_requested_explicitly(self) -> None:
        with patch("randomizer.patch.main") as native, \
                patch("randomizer.standalone.__main__.copy_patch_report"), redirect_stdout(StringIO()):
            main(["game.3ds", "--seed", "vanilla-map", "--no-open-ground-routes"])
        self.assertIn("--no-open-ground-routes", native.call_args_list[0].args[0])

    def test_existing_mod_fails_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.zip"
            output.write_bytes(b"preserve")
            with patch("randomizer.patch.main") as native, redirect_stdout(StringIO()), \
                    patch("sys.stderr", new=StringIO()), self.assertRaises(SystemExit):
                main(["game.3ds", "--output", str(output)])
            native.assert_not_called()
            self.assertEqual(output.read_bytes(), b"preserve")

    def test_catalog_only_generation_still_writes_seed_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo.json"
            with redirect_stdout(StringIO()):
                main(["--logic", "demo", "--seed", "demo-test", "--output", str(output)])
            self.assertIn('"placements"', output.read_text())

    def test_automatic_filenames_cannot_escape_generated_directory(self) -> None:
        recipe, mod = output_paths(None, "../../bad seed")
        self.assertEqual(recipe.parent, Path("generated/sticker-star-bad_seed"))
        self.assertEqual(mod.parent, recipe.parent)

    def test_failed_generation_does_not_attempt_apply(self) -> None:
        with patch("randomizer.patch.main", side_effect=SystemExit(2)) as native, redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit):
                main(["game.3ds", "--seed", "failure-test"])
        self.assertEqual(native.call_count, 1)

    def test_report_sidecar_is_the_exact_compiled_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "mod.zip"
            recipe = Path(directory) / "seed.stickerpatch"
            data = b'{"compiled-profile":"exact"}'
            with ZipFile(mod, "w") as archive:
                archive.writestr("reports/patch-report.json", data)
            copy_patch_report(mod, recipe)
            self.assertEqual(Path(str(recipe) + ".patch-report.json").read_bytes(), data)
            with self.assertRaises(FileExistsError):
                copy_patch_report(mod, recipe)

    def test_tracking_locates_report_without_an_extra_argument(self) -> None:
        from ..track_standalone import main as track

        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "seed.stickerpatch"
            report = Path(str(recipe) + ".patch-report.json")
            report.write_text("{}")
            with patch("randomizer.track_standalone.run", new_callable=AsyncMock) as observe, \
                    redirect_stdout(StringIO()):
                track(["--seed", str(recipe)])
            args = observe.call_args.args[0]
            self.assertEqual(args.patch_report, report)
            self.assertEqual(args.config, Path(str(recipe) + ".tracking.json"))
            self.assertEqual(args.tracker_data, Path(str(recipe) + ".tracker-data.json"))
