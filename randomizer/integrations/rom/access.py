"""Separate world-map navigation experiments from received admission ownership."""

import re

from .native_delivery import DeliveryPlan
from .script_build import prepend_body

WORLD_MAP_SCRIPT = "Script/WorldMap/evt_WorldMap.bin"


def configure_world_map(source: str, plan: DeliveryPlan, known_flags: set[str]) -> str:
    """Reapply grounded navigation after the original map-state refresh.

    Only route bits and ground-node visibility change; source receipts, Royal,
    Wiggler and harbor flags retain native handling. Sea edges involving X01/X02 and all sky edges
    retain native handling. The runtime-versus-save effect of wm_set_gf needs
    physical verification; callers can explicitly request vanilla navigation.
    """
    if not plan.open_ground_routes and plan.starting_stage is None:
        return source
    marker = re.compile(r"\bwm_check_gf\*?\(\);")
    matches = list(marker.finditer(source))
    if len(matches) != 1:
        raise ValueError("World-map policy needs one original state refresh")
    lines = ["\ttemp tempVar94 = rando_seed_valid*();", "\tif ( tempVar94 ) {"]
    if plan.open_ground_routes:
        routes = sorted(flag for flag in known_flags if re.fullmatch(r"gf_wm_(?:[a-e][0-9]{2}|x00)_[a-e][0-9]{2}", flag))
        if not routes:
            raise ValueError("No registered grounded map routes")
        lines.extend(f'\t\twm_set_gf*("{flag.upper()}");' for flag in routes)
        # A route bit alone is not an explicit request to display its course.
        # Show ground nodes separately, retaining admission and boat/sky gates.
        lines.extend(f'\t\twm_cspt_show*("{code}");' for code in plan.stage_access_codes
                     if re.fullmatch(r"[A-E][0-9]{2}|X00", code))
    if plan.starting_stage is not None:
        lines.extend([
            "\t\tif ( gf_rando_map_start_initialized == false ) {",
            f'\t\t\twm_set_cspt*("{plan.starting_stage}");',
            "\t\t\tgf_rando_map_start_initialized *= true;", "\t\t}",
        ])
    lines.append("\t}")
    position = matches[0].end()
    return source[:position] + "\n" + "\n".join(lines) + source[position:]


def gate_stage_entry(source: str, plan: DeliveryPlan) -> str:
    if not plan.stage_access_codes:
        raise ValueError("No configured stage admission capabilities")
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 == false ) {\n\t\treturn* false;\n\t}"]
    for code in plan.stage_access_codes:
        lines.extend(
            [
                f'\ttempVar90 = wm_is_cspt*("{code}");',
                f"\tif ( tempVar90 && gf_rando_stage_{code.lower()} == false ) {{\n\t\treturn* false;\n\t}}",
            ]
        )
    return prepend_body(source, "e_wm_map_access", "\n".join(lines) + "\n")
