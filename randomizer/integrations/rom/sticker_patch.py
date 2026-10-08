"""Experimental combat-sticker shuffle on actual game placement records.

This patch does not implement shuffled progression or Archipelago delivery.
It is a first game patch for emulator verification, not the complete requested mode.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from random import Random
from .kdm import KdmDocument
from .pickups import GamePickup, item_pickups
from .project import RomProject


@dataclass(frozen=True)
class PickupChange:
    pickup: GamePickup
    reward: str


@dataclass(frozen=True)
class StickerPatch:
    seed: str
    source_sha256: str
    patched_sha256: str
    changes: tuple[PickupChange, ...]
    data: bytes


def build_sticker_patch(source: bytes, seed: str | int) -> StickerPatch:
    document = KdmDocument(source)
    # Secret Doors are puzzle tools. Starter/tutorial and debug maps remain vanilla.
    pickups = tuple(
        pickup
        for pickup in item_pickups(document)
        if pickup.item_name.startswith("SL_")
        and pickup.item_name != "SL_DOOR"
        and pickup.map_name.startswith(
            ("w2_", "w3_", "w4_", "w5_", "w6_", "hei_", "iwa_")
        )
        and pickup.map_name not in {"hei_2_00", "hei_2_01", "hei_2_HANA"}
    )
    if not pickups:
        raise ValueError("No supported combat-sticker pickups found")
    rewards = [pickup.item_name for pickup in pickups]
    Random(str(seed)).shuffle(rewards)
    changes = tuple(
        PickupChange(pickup, reward)
        for pickup, reward in zip(pickups, rewards, strict=True)
    )
    patched = document.edit_strings(
        {change.pickup.item_field_offset: change.reward for change in changes}
    )
    # Re-parse to validate pointers, record shapes, names, and unchanged persistence flags.
    verified = {pickup.id: pickup for pickup in item_pickups(KdmDocument(patched))}
    for change in changes:
        actual = verified[change.pickup.id]
        if (
            actual.item_name != change.reward
            or actual.collection_flag != change.pickup.collection_flag
        ):
            raise ValueError("Patch verification failed")
    return StickerPatch(
        str(seed),
        hashlib.sha256(source).hexdigest(),
        hashlib.sha256(patched).hexdigest(),
        changes,
        patched,
    )


def write_sticker_patch(
    project: RomProject, output: Path, seed: str | int
) -> StickerPatch:
    filename = "Data/kdm_dispos_data.bin"
    patch = build_sticker_patch(project.read_file(filename), seed)
    report_path = output / "patch-report.json"
    if report_path.exists():
        raise FileExistsError("Output already contains a patch report")
    project.write_override(output, filename, patch.data)
    report = {
        "format_version": 1,
        "mode": "experimental_combat_stickers",
        "complete_randomizer": False,
        "emulator_verified": False,
        "archipelago_runtime": False,
        "title_id": project.inspection.title_id,
        "seed": patch.seed,
        "source_sha256": patch.source_sha256,
        "patched_sha256": patch.patched_sha256,
        "changes": [asdict(change) for change in patch.changes],
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return patch
