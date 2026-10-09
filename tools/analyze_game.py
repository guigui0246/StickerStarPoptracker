"""Survey real tables/scripts for reward-hook research, without emitting a logic catalog."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.kdm import KdmDocument
from randomizer.integrations.rom.ksm import KsmDocument, KsmValueType
from randomizer.integrations.rom.pickups import item_pickups
from randomizer.integrations.rom.project import RomProject


@dataclass(frozen=True)
class ScriptSurvey:
    file: str
    sha256: str
    reward_constants: tuple[str, ...]
    state_variables: tuple[str, ...]
    reward_functions: tuple[str, ...]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export observed game metadata; access rules are not inferred.")
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = RomProject(args.rom)
    tables: dict[str, tuple[str, ...]] = {}
    scripts: list[ScriptSurvey] = []
    for entry in project.inspection.romfs:
        if entry.name.startswith("Data/kdm_") and entry.name.endswith(".bin"):
            document = KdmDocument(project.read_file(entry.name))
            tables[entry.name] = tuple(document.tables)
        if entry.name.startswith("Script/") and entry.name.endswith(".bin"):
            data = project.read_file(entry.name)
            script = KsmDocument(data)
            scripts.append(
                ScriptSurvey(
                    entry.name,
                    hashlib.sha256(data).hexdigest(),
                    tuple(
                        variable.value
                        for variable in script.constants
                        if isinstance(variable.value, str) and variable.value.startswith(("SL_", "REAL_", "PK_", "IC_"))
                    ),
                    tuple(
                        variable.name
                        for variable in script.statics
                        if variable.type == KsmValueType.SAVE_VARIABLE and variable.name is not None
                    ),
                    tuple(
                        imported.name
                        for imported in script.imports
                        if any(
                            word in imported.name
                            for word in (
                                "pouch_",
                                "item_get",
                                "set_flag",
                                "honor",
                                "museum",
                            )
                        )
                    ),
                )
            )
    pickups = item_pickups(KdmDocument(project.read_file("Data/kdm_dispos_data.bin")))
    report = {
        "title_id": project.inspection.title_id,
        "product_code": project.inspection.product_code,
        "verified_logic_catalog": False,
        "counts": {
            "kdm_files": len(tables),
            "scripts": len(scripts),
            "item_records": len(pickups),
        },
        "tables": tables,
        "scripts": [asdict(script) for script in scripts],
        "pickups": [asdict(pickup) for pickup in pickups],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["counts"])


if __name__ == "__main__":
    main()
