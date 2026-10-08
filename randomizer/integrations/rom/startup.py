"""Fresh-save tutorial bypass with no shuffled ability or sticker grants."""

import struct

from .kdm import KdmDocument
from .pickups import record
from .script_build import replace_body

STARTUP_SCRIPT = "Script/Map/MAC/mac_1_31.bin"
STARTUP_FLAGS = ("gf_evt_mac_mario_wakeup", "gf_evt_mac_mario_ore8", "gf_pouch_get_sealbook",
                 "gf_evt_mac_maki_help", "gf_evt_mac_hiroba_1st", "gf_mac_1_roll_evt_end",
                 "gf_evt_mac_battle_tutorial", "gf_evt_mac_battle_tutorial_end",
                 *(f"gf_evt_mac_maki_kinopio{index}" for index in range(1, 15)))


def post_tutorial_start(source: str) -> str:
    lines = ["\tif ( gf_evt_mac_mario_wakeup ) {\n\t\tsw_bero_enter*(\"af_sw_bero\");\n\t\treturn*;\n\t}",
             "\trando_deliver*();"]
    lines.extend(f"\t{flag} *= true;" for flag in STARTUP_FLAGS)
    # The inspected player controller uses accessory bit 2 for the album.
    # Hammer bit 1 and Paperization/Kersti bit 4 are filtered by the ARM guard.
    lines.extend(["\tpouch_attach_accessory*(2);", "\tui_enable_open_status_all*();",
                  '\tmap_exit_event*("af_sw_bero", 0);'])
    return replace_body(source, "sw_bero_enter_evt", "\n".join(lines))


def route_start_to_world_map(data: bytes) -> bytes:
    document = KdmDocument(data)
    rows = [record(row, 9) for array in document.arrays.values() if array.type_id == 21 for row in array.values]
    originals = [row for row in rows if [field.value for field in row[3:7]] == ["mac_1_31", "af_sw_bero", "mac_1_30", "af_ne_bero"]]
    templates = [row for row in rows if [field.value for field in row[3:7]] == ["mac_1_00", "af_s_bero", "mac_1_00", "af_s_bero"]]
    if len(originals) != 1 or len(templates) != 1 or [field.value for field in templates[0][:3]] != [3, 4, -1]:
        raise ValueError("Startup and world-map exit links do not match the inspected revision")
    original = originals[0]
    result = bytearray(document.edit_strings({original[5].offset: "mac_1_00", original[6].offset: "af_s_bero"}))
    for field, template in zip(original[:3], templates[0][:3], strict=True):
        if type(template.value) is not int:
            raise ValueError("World-map link type is not an integer")
        struct.pack_into("<i", result, field.offset, template.value)
    KdmDocument(bytes(result))
    return bytes(result)
