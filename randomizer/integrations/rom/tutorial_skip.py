"""Build an experimental skip to Decalburg's unrolling event.

Requires the MIT-licensed Longboost/gibberish compiler checkout. Game scripts
are extracted from the user's dump and remain in the ignored output folder.
"""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .ksm import KsmDocument
from .kdm import KdmDocument
from .project import RomProject


def replace_function(source: str, name: str, body: str) -> str:
    """Replace one private function body, preserving all other source text."""
    marker = f"private {name}()  {{"
    if source.count(marker) != 1:
        raise ValueError(f"Expected exactly one function: {name}")
    start = source.index(marker) + len(marker)
    end = start
    depth = 1
    while depth:
        end += 1
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
    return source[:start] + "\n" + body + "\n" + source[end:]


def compile_script(compiler: Path, file: Path) -> None:
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("compiler_driver.py")), str(compiler), str(file)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def route_to_unrolling_entrance(data: bytes) -> bytes:
    """Use the east arrival, whose vanilla script starts the unrolling event."""
    document = KdmDocument(data)
    matches = [
        fields
        for array in document.arrays.values()
        if array.type_id == 21
        for record in array.values
        if isinstance(fields := record.value, tuple)
        and len(fields) == 9
        and fields[3].value == "mac_1_31"
        and fields[4].value == "af_sw_bero"
        and fields[5].value == "mac_1_30"
        and fields[6].value == "af_ne_bero"
    ]
    if len(matches) != 1:
        raise ValueError("Expected one introductory plaza exit to the rolled plaza")
    return document.edit_strings({matches[0][6].offset: "af_e_bero"})


def write_tutorial_skip(project: RomProject, output: Path, compiler: Path) -> None:
    compiler = compiler.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Use a new output folder to preserve existing mods")
    work = output / "build"
    work.mkdir(parents=True)
    setup = [
        "gf_evt_mac_mario_wakeup *= true;",
        "gf_evt_mac_mario_ore8 *= true;",
        "gf_pouch_get_sealbook *= true;",
        "gf_evt_mac_maki_help *= true;",
        "gf_evt_mac_hiroba_1st *= true;",
        *[f"gf_evt_mac_maki_kinopio{i} *= true;" for i in range(1, 15)],
        *[
            f'mobj_set_flag_ex*("MAC_1", "mac_1_31", "{flag}");'
            for flag in ("paste_seal01", "paste_seal02", "BLK_01", "paste_seal06")
        ],
        'item_try_addpouch*("IC_HAMMER", true);',
        'player_set_ignore_key*("mario", player_hammer_button, false);',
        "ui_enable_open_status_all*();",
        *[
            f'item_try_addpouch*("{item}", true);'
            for item in ("SL_JUMP",) * 4 + ("SL_HAMMER",) * 4 + ("SL_KINOKO",) * 2
        ],
        'map_exit_event*("af_sw_bero", 0);',
    ]
    body = (
        '\tif ( gf_evt_mac_mario_wakeup ) {\n\t\tsw_bero_enter*("af_sw_bero");\n\t\treturn*;\n\t}\n\t'
        + "\n\t".join(setup)
    )
    edits = {"Script/Map/MAC/mac_1_31.bin": ("sw_bero_enter_evt", body)}
    report: dict[str, object] = {
        "status": "experimental; in-game validation required",
        "target": "rolled Decalburg before unrolling",
        "opening_movie": "preserved",
        "files": [],
    }
    files: list[dict[str, str]] = []
    for name, (function, body) in edits.items():
        original = project.read_file(name)
        binary = work / Path(name).name
        binary.write_bytes(original)
        compile_script(compiler, binary)
        source = binary.with_suffix(".cksm")
        text = replace_function(source.read_text(encoding="utf-8"), function, body)
        source.write_text(text, encoding="utf-8")
        if "map_exit_event*" in body:
            header = binary.with_suffix(".hksm")
            header.write_text(
                header.read_text(encoding="utf-8")
                + "\n#import function map_exit_event from 0xf5 {0x44e};\n"
                "#import function mobj_set_flag_ex from 0x135 {0x184};\n"
                "#import function item_try_addpouch from 0x1a7 {0x82a};\n"
                "static user gf_evt_mac_hiroba_1st;\n",
                encoding="utf-8",
            )
        compile_script(compiler, source)
        rebuilt = binary.with_suffix(".re.bin")
        patch = rebuilt.read_bytes()
        KsmDocument(patch)
        compile_script(compiler, rebuilt)
        canonical = rebuilt.with_suffix(".cksm").read_text(encoding="utf-8")
        if body not in canonical:
            raise ValueError(
                f"Compiled replacement did not survive decompilation: {name}"
            )
        project.write_override(output, name, patch)
        files.append(
            {
                "name": name,
                "original_sha256": hashlib.sha256(original).hexdigest(),
                "patched_sha256": hashlib.sha256(patch).hexdigest(),
            }
        )
    report["files"] = files
    links_name = "Data/kdm_link_data.bin"
    original_links = project.read_file(links_name)
    patched_links = route_to_unrolling_entrance(original_links)
    project.write_override(output, links_name, patched_links)
    files.append(
        {
            "name": links_name,
            "original_sha256": hashlib.sha256(original_links).hexdigest(),
            "patched_sha256": hashlib.sha256(patched_links).hexdigest(),
        }
    )
    report["revision"] = 2
    report["arrival"] = "east entrance; vanilla unrolling event starts automatically"
    report["starting_stickers"] = {"SL_JUMP": 4, "SL_HAMMER": 4, "SL_KINOKO": 2}
    (output / "patch-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (output / "README.txt").write_text(
        "Experimental tutorial skip, European Sticker Star 00040000000A5F00.\n"
        "Close Citra. Back up your existing mod folder. Use this romfs folder alone\n"
        "under Citra's Open Mods Location for this game. Start a NEW save slot.\n"
        "The opening movie remains. The field tutorial should be skipped to the\n"
        "rolled plaza with Toads rescued. Unrolling should start automatically.\n"
        "Starting inventory: hammer, 4 Jump, 4 Hammer, and 2 Mushroom stickers.\n"
        "Replace the earlier test's entire romfs folder: this revision contains\n"
        "BOTH Script/Map/MAC/mac_1_31.bin and Data/kdm_link_data.bin.\n"
        "This test does not shuffle stickers. Existing saves are not migrated.\n"
        "Script compilation verified; playable transition not yet verified.\n",
        encoding="utf-8",
    )


