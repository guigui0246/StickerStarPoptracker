import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ..integrations.rom.seed_patch import (
    PLACEMENTS,
    TUTORIAL_FILES,
    PatchRecipe,
    apply_recipe,
    canonical,
    create_recipe,
    decode_recipe,
    digest,
    write_recipe,
)
from ..integrations.rom.sticker_patch import StickerPatch, PickupChange
from ..integrations.rom.pickups import GamePickup


class SeedPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = b"synthetic source, not game content"
        self.patched = b"synthetic patched data"
        self.recipe = PatchRecipe("42", False, {PLACEMENTS: digest(self.source)}, digest(self.patched), 1)
        pickup = GamePickup("test_map", "test_object", "SL_JUMP", 100, 17, 0.0, 0.0, 0.0)
        self.patch = StickerPatch(
            "42", digest(self.source), digest(self.patched), (PickupChange(pickup, "SL_HAMMER"),), self.patched
        )

    def altered(self, **changes: object) -> bytes:
        payload = json.loads(self.recipe.encode())
        payload.pop("recipe_sha256")
        payload.update(changes)
        payload["recipe_sha256"] = digest(canonical(payload))
        return canonical(payload)

    def test_roundtrip_contains_recipe_only_and_is_deterministic(self) -> None:
        self.assertEqual(decode_recipe(self.recipe.encode()), self.recipe)
        self.assertEqual(self.recipe.encode(), self.recipe.encode())
        self.assertNotIn(self.source, self.recipe.encode())
        self.assertNotIn(self.patched, self.recipe.encode())
        self.assertNotIn("data", json.loads(self.recipe.encode()))

    def test_strict_versions_settings_checksums_and_paths(self) -> None:
        for changes in (
            {"format_version": True},
            {"format_version": 2},
            {"algorithm": "unknown"},
            {"mode": "full_progression"},
            {"title_id": "other"},
            {"tutorial_skip_revision": True},
            {"tutorial_skip_revision": 1},
            {"pickup_count": True},
            {"pickup_count": 0},
            {"seed": ""},
            {"seed": "x" * 1025},
            {"placements_sha256": "invalid"},
            {"unknown": 1},
            {"source_hashes": {"../../escape": digest(self.source)}},
            {"tutorial_skip_revision": 2},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                decode_recipe(self.altered(**changes))
        for data in (b"[]", b"{", b"x" * 16385, self.recipe.encode().replace(b'"42"', b'"43"'), b'{"seed":1,"seed":2}'):
            with self.assertRaises(ValueError):
                decode_recipe(data)

    def test_generation_binds_the_exact_source_and_tutorial_files(self) -> None:
        project = Mock()
        project.read_file.side_effect = lambda name: self.source if name == PLACEMENTS else name.encode()
        with patch("randomizer.integrations.rom.seed_patch.build_sticker_patch", return_value=self.patch):
            recipe = create_recipe(project, 42, True)
        self.assertTrue(recipe.tutorial_skip)
        self.assertEqual(set(recipe.source_hashes), {PLACEMENTS, *TUTORIAL_FILES})
        self.assertEqual(recipe.placements_sha256, digest(self.patched))

    def test_application_is_atomic_preserves_existing_mod_and_rejects_wrong_dump(self) -> None:
        project = Mock()
        project.read_file.return_value = self.source

        def write_override(output: Path, name: str, data: bytes) -> None:
            target = output / "romfs" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        project.write_override.side_effect = write_override
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mod"
            with patch("randomizer.integrations.rom.seed_patch.build_sticker_patch", return_value=self.patch):
                apply_recipe(project, self.recipe, output)
                self.assertEqual((output / "romfs" / PLACEMENTS).read_bytes(), self.patched)
                self.assertEqual(json.loads((output / "patch-report.json").read_text())["changed_pickups"], 1)
                with self.assertRaises(FileExistsError):
                    apply_recipe(project, self.recipe, output)
                project.read_file.return_value = b"wrong dump"
                with self.assertRaises(ValueError):
                    apply_recipe(project, self.recipe, Path(directory) / "wrong")
                self.assertFalse((Path(directory) / "wrong").exists())

    def test_failed_build_never_publishes_a_partial_mod(self) -> None:
        project = Mock()
        project.read_file.return_value = self.source
        project.write_override.side_effect = OSError("disk full")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mod"
            with patch("randomizer.integrations.rom.seed_patch.build_sticker_patch", return_value=self.patch):
                with self.assertRaises(OSError):
                    apply_recipe(project, self.recipe, output)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_recipe_writes_never_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "seed.stickerpatch"
            write_recipe(self.recipe, target)
            with self.assertRaises(FileExistsError):
                write_recipe(self.recipe, target)
            self.assertEqual(target.read_bytes(), self.recipe.encode())

    def test_missing_compiler_and_changed_algorithm_fail_before_writing(self) -> None:
        project = Mock()
        project.read_file.return_value = self.source
        tutorial = PatchRecipe(
            "42",
            True,
            {PLACEMENTS: digest(self.source), **{name: digest(self.source) for name in TUTORIAL_FILES}},
            digest(self.patched),
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "mod"
            with self.assertRaises(ValueError):
                apply_recipe(project, tutorial, output)
            changed = StickerPatch("42", digest(self.source), digest(b"changed"), self.patch.changes, b"changed")
            with patch("randomizer.integrations.rom.seed_patch.build_sticker_patch", return_value=changed):
                with self.assertRaises(ValueError):
                    apply_recipe(project, self.recipe, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
