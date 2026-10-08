"""Portable, asset-free recipes for the verified experimental patch modes.

Artifacts contain seed/settings and hashes only. Game bytes are read from the
recipient's dump at application time. Algorithms are explicitly versioned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import tempfile

from ...data.catalog import Json, obj, string
from .project import RomProject, publish_directory
from .sticker_patch import build_sticker_patch
from .tutorial_skip import write_tutorial_skip


TITLE_ID = "00040000000A5F00"
PLACEMENTS = "Data/kdm_dispos_data.bin"
TUTORIAL_FILES = ("Script/Map/MAC/mac_1_31.bin", "Data/kdm_link_data.bin")
ALGORITHM = "combat-stickers-v1"
MAX_ARTIFACT_BYTES = 16384


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def keys(data: dict[str, Json], expected: set[str]) -> None:
    if set(data) != expected:
        raise ValueError("Unsupported or missing stickerpatch fields")


def sha256(value: Json) -> str:
    result = string(value)
    if len(result) != 64 or any(char not in "0123456789abcdef" for char in result):
        raise ValueError("Expected a lowercase SHA-256 hash")
    return result


@dataclass(frozen=True)
class PatchRecipe:
    seed: str
    tutorial_skip: bool
    source_hashes: dict[str, str]
    placements_sha256: str
    pickup_count: int

    def payload(self) -> dict[str, Json]:
        return {
            "format_version": 1,
            "algorithm": ALGORITHM,
            "mode": "experimental_combat_stickers",
            "title_id": TITLE_ID,
            "seed": self.seed,
            "tutorial_skip_revision": 2 if self.tutorial_skip else 0,
            "source_hashes": dict(self.source_hashes),
            "placements_sha256": self.placements_sha256,
            "pickup_count": self.pickup_count,
        }

    def encode(self) -> bytes:
        payload = self.payload()
        payload["recipe_sha256"] = digest(canonical(payload))
        return canonical(payload) + b"\n"


def canonical(payload: dict[str, Json]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def unique_object(pairs: list[tuple[str, Json]]) -> dict[str, Json]:
    result: dict[str, Json] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate stickerpatch JSON field")
        result[name] = value
    return result


def decode_recipe(data: bytes) -> PatchRecipe:
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("Stickerpatch exceeds the supported size")
    try:
        payload = obj(json.loads(data, object_pairs_hook=unique_object))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid stickerpatch JSON") from exc
    keys(payload, {
        "format_version", "algorithm", "mode", "title_id", "seed",
        "tutorial_skip_revision", "source_hashes", "placements_sha256",
        "pickup_count", "recipe_sha256",
    })
    checksum = sha256(payload.pop("recipe_sha256"))
    if checksum != digest(canonical(payload)):
        raise ValueError("Stickerpatch checksum mismatch")
    if type(payload["format_version"]) is not int or payload["format_version"] != 1:
        raise ValueError("Unsupported stickerpatch version")
    if (
        payload["algorithm"] != ALGORITHM
        or payload["mode"] != "experimental_combat_stickers"
        or payload["title_id"] != TITLE_ID
    ):
        raise ValueError("Unsupported stickerpatch algorithm, mode, or title")
    revision = payload["tutorial_skip_revision"]
    if type(revision) is not int or revision not in (0, 2):
        raise ValueError("Unsupported tutorial skip revision")
    count = payload["pickup_count"]
    if type(count) is not int or count < 1:
        raise ValueError("Expected a positive pickup count")
    seed = string(payload["seed"])
    if len(seed) > 1024:
        raise ValueError("Seed is too long")
    sources = obj(payload["source_hashes"])
    keys(sources, {PLACEMENTS, *(TUTORIAL_FILES if revision else ())})
    return PatchRecipe(
        seed, bool(revision), {name: sha256(value) for name, value in sources.items()},
        sha256(payload["placements_sha256"]), count,
    )


def create_recipe(project: RomProject, seed: str | int, tutorial_skip: bool = False) -> PatchRecipe:
    patch = build_sticker_patch(project.read_file(PLACEMENTS), seed)
    hashes = {PLACEMENTS: patch.source_sha256}
    if tutorial_skip:
        hashes.update({name: digest(project.read_file(name)) for name in TUTORIAL_FILES})
    recipe = PatchRecipe(str(seed), tutorial_skip, hashes, patch.patched_sha256, len(patch.changes))
    # Use the same boundary validation for generated and loaded artifacts.
    return decode_recipe(recipe.encode())


def write_recipe(recipe: PatchRecipe, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(recipe.encode())


def apply_recipe(
    project: RomProject, recipe: PatchRecipe, output: Path, compiler: Path | None = None,
) -> Path:
    """Validate completely, build in isolation, publish only a complete folder."""
    recipe = decode_recipe(recipe.encode())
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Use a new output folder to preserve existing mods")
    if recipe.tutorial_skip and compiler is None:
        raise ValueError("Tutorial skip requires --compiler pointing to Gibberish main.py")
    for name, expected in recipe.source_hashes.items():
        if digest(project.read_file(name)) != expected:
            raise ValueError(f"ROM file does not match this seed: {name}")
    patch = build_sticker_patch(project.read_file(PLACEMENTS), recipe.seed)
    if patch.patched_sha256 != recipe.placements_sha256 or len(patch.changes) != recipe.pickup_count:
        raise ValueError("Patch algorithm output does not match the recipe")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stickerpatch-", dir=output.parent) as temporary:
        staging = Path(temporary) / "mod"
        if recipe.tutorial_skip:
            assert compiler is not None
            write_tutorial_skip(project, staging, compiler)
        project.write_override(staging, PLACEMENTS, patch.data)
        overrides = sorted((staging / "romfs").rglob("*.bin"))
        report = {
            "format_version": 1,
            "mode": "experimental_combat_stickers",
            "complete_randomizer": False,
            "emulator_verified": False,
            "archipelago_runtime": False,
            "recipe": json.loads(recipe.encode()),
            "changed_pickups": sum(change.pickup.item_name != change.reward for change in patch.changes),
            "changes": [asdict(change) for change in patch.changes],
            "overrides": {
                path.relative_to(staging / "romfs").as_posix(): digest(path.read_bytes())
                for path in overrides
            },
        }
        (staging / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (staging / "README.txt").write_text(
            f"Experimental Sticker Star combat shuffle, seed {recipe.seed}.\n"
            f"European title {TITLE_ID}. Progression and AP delivery are unfinished.\n"
            "Close your emulator, back up existing mods, and install the romfs folder\n"
            "under this title's Open Mods Location. Use this generated folder alone.\n"
            "The original ROM and your saves have not been modified.\n"
            + ("Tutorial skip enabled: start a NEW save slot. Opening movie remains.\n"
               "Starts with Hammer, 4 Jump, 4 Hammer and 2 Mushroom stickers.\n"
               if recipe.tutorial_skip else "Tutorial and starting inventory are vanilla.\n"),
            encoding="utf-8",
        )
        # Path.rename fails if a destination directory already exists on Windows;
        # checking again also protects platforms that replace empty directories.
        if output.exists() or output.is_symlink():
            raise FileExistsError("Output appeared while building; refusing to replace it")
        publish_directory(staging, output)
    return output
