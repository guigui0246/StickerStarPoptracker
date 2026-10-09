import sys
import unittest
from unittest.mock import Mock, patch

from tools import release_cli
from ..patch import main as patch_recipe


class ReleaseCliTests(unittest.TestCase):
    def test_legacy_direct_patch_arguments_keep_working(self) -> None:
        with patch.object(release_cli, "combat_patch") as combat, patch.object(
            sys, "argv", ["cli_randomizer", "patch", "ROM path.3ds", "--seed", "42", "--output", "mod"]
        ):
            release_cli.main()
            combat.assert_called_once_with()
            self.assertEqual(sys.argv[1], "ROM path.3ds")

    def test_source_entry_uses_same_generate_command(self) -> None:
        from .. import __main__ as source

        command = Mock()
        with patch.dict(release_cli.COMMANDS, {"generate": command}), patch.object(
            sys, "argv", ["randomizer", "generate", "--seed", "42", "--output", "seed.json"]
        ):
            source.main()
            command.assert_called_once_with()

    def test_source_gui_uses_current_python(self) -> None:
        from tools.release_gui import cli_command

        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(cli_command(), [sys.executable, "-m", "tools.release_cli"])

    def test_patch_dispatch_exposes_native_recipes(self) -> None:
        self.assertIs(release_cli.COMMANDS["patch"], patch_recipe)
        command = Mock()
        with patch.dict(release_cli.COMMANDS, {"patch": command}), patch.object(
            sys, "argv", ["cli_randomizer", "patch", "generate-native-catalog", "--seed", "42"]
        ):
            release_cli.main()
            self.assertEqual(sys.argv[1:], ["generate-native-catalog", "--seed", "42"])
            command.assert_called_once_with()

    def test_internal_compiler_command_preserves_paths_and_does_not_enter_regular_dispatch(self) -> None:
        with patch.object(release_cli, "compile_script") as compiler, patch.object(
            sys, "argv", ["cli_randomizer", "_compile-script", "compiler path/main.py", "source path/script.cksm"]
        ):
            release_cli.main()
            self.assertEqual(sys.argv, ["cli_randomizer", "compiler path/main.py", "source path/script.cksm"])
            compiler.assert_called_once_with()
