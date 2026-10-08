"""World-map entry gates that preserve native traversal and admission checks."""

from .native_delivery import DeliveryPlan
from .script_build import prepend_body

WORLD_MAP_SCRIPT = "Script/WorldMap/evt_WorldMap.bin"


def gate_stage_entry(source: str, plan: DeliveryPlan) -> str:
    if not plan.stage_access_codes:
        raise ValueError("No configured stage admission capabilities")
    lines = ["\ttemp tempVar90 = rando_seed_valid*();", "\tif ( tempVar90 == false ) {\n\t\treturn* false;\n\t}"]
    for code in plan.stage_access_codes:
        lines.extend([f'\ttempVar90 = wm_is_cspt*("{code}");',
                      f"\tif ( tempVar90 && gf_rando_stage_{code.lower()} == false ) {{\n\t\treturn* false;\n\t}}"])
    return prepend_body(source, "e_wm_map_access", "\n".join(lines) + "\n")
