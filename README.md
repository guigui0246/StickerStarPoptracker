# Sticker Star tools

The repository contains a PopTracker pack, a standalone randomizer engine,
experimental ROM integrations and an Archipelago Logic Demo.

## Builds

Use Python 3.12 or later on Linux or Windows:

```text
python -m pip install -r requirements-build.txt
python build.py cli_randomizer apworld randomizer tracker
```

Outputs go to `generated/`. Individual targets may be selected. The GUI build
requires successfully built `cli_randomizer` and `sticker-star.apworld` files;
use `--dependencies DIRECTORY` to supply them from another build.
Use `--output DIRECTORY` to change the output directory.

The CLI supports `generate`, `patch`, `track`, `client` and `catalog` subcommands.

See [human_tests.todo](human_tests.todo) for gameplay and packaged-release validation.
Start with `@critical` entries; `@blocked` entries identify prerequisites for full playthroughs.
For example, `cli_randomizer generate --help` describes generation options.
From source, use `python -m randomizer generate` with the same arguments.
Without `--catalog`, generation uses the small logic demo, not the full game.
Seed JSON lists every randomized placement in the selected catalog, fixed rewards
separately, and location/item names. The complete reviewed game catalog remains unfinished.
`patch ROM.3ds --seed SEED --output MOD` retains the original combat-only patch mode;
recipe workflows use `patch generate`, `patch generate-native-catalog` and `patch apply`.
Logic-demo seed JSON from `generate` cannot be passed to `patch apply`.
For an experimental combat shuffle, use these source commands (replace `ROM.3ds` with your ROM path):

```text
python -m randomizer.patch generate "ROM.3ds" --seed 18 --output seed-18.stickerpatch
python -m randomizer.patch apply seed-18.stickerpatch "ROM.3ds" --output mod-18
```

The apply output is a mod directory, not a ZIP archive. This mode shuffles combat
stickers; it does not implement the unfinished full-game progression catalog.
The GUI runs these same commands and installs the bundled APWorld into an
Archipelago installation's `custom_worlds` directory. The APWorld is currently
the Logic Demo; these builds do not make unfinished native progression playable.

Tracker packaging uses an explicit list of runtime directories and the manifest,
excluding development scripts and source art projects. The PowerShell tracker
build script delegates to the cross-platform Python builder.

## Automation

GitHub Actions runs one job for each of the four targets on each OS.
Both GUI builds wait for the initial six builds to succeed and consume their
own OS's CLI and APWorld artifacts. The final job checks for exactly eight
nonempty assets and gives every asset an OS-specific name before publishing a
new prerelease. Linux executables target x86-64 with Ubuntu 22.04's glibc baseline.

Pushes to `main` or `master` and manual workflow runs publish prereleases.
Pull requests build all targets without publishing. Release tags include the
workflow run ID and attempt, so reruns create distinct prereleases.

See [randomizer documentation](randomizer/README.md) and
[tracker documentation](tracker/README.md) for the existing tools.

## Code checks

Flake8 uses a 127-character limit; Pyright uses basic checking for Python 3.12.
Test casts describe dynamic fixture values and deliberately invalid inputs.
Specific missing-import annotations identify optional dependencies loaded from
user-supplied Archipelago, Lua or ARM emulator installations. These dependencies
are required when running those integration tools.
