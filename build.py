"""Build release packages without starting applications."""

import argparse
from pathlib import Path
import platform
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
TARGETS = ("cli_randomizer", "apworld", "randomizer", "tracker")


def run(*arguments: str) -> None:
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)


def executable(target: str, output: Path, dependencies: Path) -> None:
    entry = ROOT / "tools" / "release_cli.py"
    arguments = [
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        target,
        "--distpath",
        str(output),
        "--workpath",
        str(ROOT / "build" / target),
        "--specpath",
        str(ROOT / "build" / target),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "websockets.asyncio.client",
        "--hidden-import",
        "websockets.asyncio.server",
        "--hidden-import",
        "websockets.exceptions",
        "--hidden-import",
        "array",
    ]
    if target == "cli_randomizer":
        arguments.extend(("--add-data", f"{ROOT / 'vendor' / 'gibberish'}:bundled/gibberish"))
        for filename in ("bindings.json", "native_reference.json"):
            arguments.extend(("--add-data", f"{ROOT / 'randomizer' / 'data' / 'game' / filename}:bundled/game"))
    if target == "randomizer":
        entry = ROOT / "tools" / "release_gui.py"
        for filename in ("sticker-star.apworld", "cli_randomizer.exe" if sys.platform == "win32" else "cli_randomizer"):
            dependency = dependencies / filename
            if not dependency.is_file():
                raise FileNotFoundError(f"Build cli_randomizer and apworld first: missing {dependency}")
            arguments.extend(("--add-data", f"{dependency}:bundled"))
        arguments.append("--windowed")
    run(*arguments, str(entry))


def tracker(output: Path) -> None:
    source = ROOT / "tracker"
    with ZipFile(output / "sticker-star-poptracker.zip", "w", ZIP_DEFLATED) as archive:
        for folder in ("images", "items", "layouts", "locations", "maps", "scripts"):
            for path in sorted((source / folder).rglob("*")):
                if path.is_file() and path.suffix != ".kra" and "__pycache__" not in path.parts:
                    archive.write(path, "sticker-star/" + path.relative_to(source).as_posix())
        archive.write(source / "manifest.json", "sticker-star/manifest.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", choices=TARGETS)
    parser.add_argument("--output", type=Path, default=ROOT / "generated")
    parser.add_argument("--dependencies", type=Path, help="Directory containing previously built CLI and APWorld")
    parser.add_argument("--release", action="store_true", help="Give outputs unique OS/architecture names")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    dependencies = args.dependencies.resolve() if args.dependencies else output
    suffix = f"{platform.system().lower()}-{platform.machine().lower()}"
    outputs: list[Path] = []
    for target in TARGETS:
        if target not in args.targets:
            continue
        if target == "apworld":
            run(str(ROOT / "tools" / "build_apworld.py"), "--output", str(output / "sticker-star.apworld"))
            filename = "sticker-star.apworld"
        elif target == "tracker":
            tracker(output)
            filename = "sticker-star-poptracker.zip"
        else:
            executable(target, output, dependencies)
            filename = target + (".exe" if sys.platform == "win32" else "")
        outputs.append(output / filename)
    if args.release:
        for path in outputs:
            path.rename(path.with_name(f"{path.stem}-{suffix}{path.suffix}"))


if __name__ == "__main__":
    main()
