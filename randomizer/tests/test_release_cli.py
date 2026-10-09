import sys
import unittest
from unittest.mock import Mock, patch

from tools import release_cli
from ..patch import main as patch_recipe


class ReleaseCliTests(unittest.TestCase):
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
