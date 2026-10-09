# Sticker Star tools

The repository contains a PopTracker pack, a standalone randomizer engine,
ROM-derived experimental no-logic seeds and an Archipelago Logic Demo.

## Standalone no-logic seeds

Generate directly from your decrypted European ROM in one command:

```text
python -m randomizer generate --logic no-logic "ROM.3ds"
```

The seed defaults to random. Output defaults to `generated/sticker-star-SEED/`,
containing `mod.zip`, `seed.stickerpatch`, its matching PopTracker pack, and
tracking/logic sidecars. The compiler is included and the mod is built
automatically. `--rom "ROM.3ds"` is also accepted. To reproduce a seed or choose
the output, add `--seed 42 --output generated/my-seed` (a `.zip` filename is also
accepted). Settings such as `--album-pages randomized --museum off` go directly
on this same command.

The JSON `.stickerpatch` contains identities, placements and hashes, without
ROM bytes or game assets. Applying it needs only that file, the matching ROM
and the compiler tool. The mod ZIP contains `00040000000A5F00/romfs` and
`00040000000A5F00/exefs`; install that title folder in the emulator's `load/mods`
folder and use a new save. Keep the seed and tracker sidecars together.

Load `seed.stickerpatch.tracker.zip` in PopTracker. Enable the emulator's
UDP RPC server on port 45987, start the game, then run:

```text
python -m pip install "websockets>=13,<16"
python -m randomizer track --seed generated/sticker-star-SEED/seed.stickerpatch
```

Connect PopTracker's Archipelago interface to `localhost:38281`, slot `Player`,
with no password. This loopback server only observes the game; standalone
rewards do not need it or emulator RPC. Collected checks and successfully
delivered items are tracked independently, with replay after reconnect/load.
On the tested Citra 608383e installation, native startup and the packaged
bridge were verified with hardware shaders and shader JIT disabled; the
default shader configuration crashed even with the unmodified ROM.

No-logic includes every discovered production check and unique progression
reward, with coin filler. Bowser victory remains fixed. Hammer, Paperization,
Decalburg and 1-1 access are starting capabilities. The starting Jump is a copy,
so it becomes a small slipper until its shuffled Jump unlock is received.
Ground routes and course visibility are opened independently by default;
entering a course still needs its stage-access item. Use
`--no-open-ground-routes` to request vanilla navigation. Options include vanilla,
all-at-start or randomized pages, museum categories, enemy checks, vanilla door
places, generic sticker availability and banner thresholds. Random ground-stage
starts are available as an opt-in experiment.
Each seed also exports an editable catalog and native bindings for adding logic.
Permanent authoring files are in [randomizer/data/game](randomizer/data/game/README.md):
edit typed objects in `items.py`, `locations.py`, `regions.py` and `paths.py`, then run
`python -m randomizer generate --logic catalog "ROM.3ds"` to use your edits.
The initial physical links are explicitly no-logic placeholders.
See [the implementation guide](docs/IMPLEMENTATION_GUIDE.md) for commands,
option semantics, rule examples, module responsibilities and troubleshooting.
Tracker access is unconditional; native puzzles, boat/sky routes and admission
requirements remain. No-logic does not guarantee a completable seed. The
complete definition of done, physical traversal and full playthrough validation
remain unfinished; this workflow is an experimental native randomizer.

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

The CLI supports `generate`, `patch`, `track`, `client`, `catalog` and `rebind` subcommands.

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

Combat-only apply output is a mod directory. Native apply also accepts a `.zip`
output containing the title-ID installation folder. Combat-only mode shuffles combat
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
