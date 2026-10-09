"""First-peel checks that preserve later restoration and re-peeling."""

from collections import defaultdict
from dataclasses import dataclass

from .kdm import KdmDocument
from .native_delivery import DeliveryPlan, NativeReward, PeelReward, PeelVariant
from .paperization import PaperizationLock, paperization_locks
from .pickups import record, text
from .script_build import prepend_body


@dataclass(frozen=True)
class PeelSource:
    map_name: str
    completion_flag: str
    callback: str
    cancel_callback: str
    variants: tuple[PeelVariant, ...]

    def check(self, reward: NativeReward) -> PeelReward:
        first = self.variants[0]
        return PeelReward(self.map_name, first.lock_id, first.source_item, reward, self.variants[1:])


def peel_sources(document: KdmDocument) -> tuple[PeelSource, ...]:
    locks = paperization_locks(document)
    pickup_ids = {
        text(record(row, 72)[0])
        for array in document.arrays.values()
        if array.type_id == 21
        for row in array.values
        if record(row, 72)[2].value is True
    }
    groups: dict[tuple[str, str, str], list[PaperizationLock]] = defaultdict(list)
    for lock in locks:
        if not lock.key_item.startswith("PK_"):
            continue
        if lock.id not in pickup_ids or not lock.completion_flag or not lock.callbacks[2]:
            raise ValueError("Scrap lock lacks an observed pickup completion callback")
        groups[(lock.map_name, lock.completion_flag, lock.callbacks[2])].append(lock)
    result = []
    for (map_name, flag, callback), members in sorted(groups.items()):
        ids = {lock.id for lock in members}
        if any(lock.id not in ids and (lock.map_name, lock.callbacks[2]) == (map_name, callback) for lock in locks):
            raise ValueError("Peel callback is shared with an unrelated paperization operation")
        variants = tuple(PeelVariant(lock.id, lock.key_item) for lock in sorted(members, key=lambda lock: lock.id))
        if len({lock.callbacks[3] for lock in members}) != 1 or not members[0].callbacks[3]:
            raise ValueError("Peel source lacks one cancellation callback")
        result.append(PeelSource(map_name, flag, callback, members[0].callbacks[3], variants))
    return tuple(result)


def resolve_peels(document: KdmDocument, plan: DeliveryPlan) -> tuple[tuple[int, PeelReward, PeelSource], ...]:
    observed = {(source.map_name, source.variants[0].lock_id): source for source in peel_sources(document)}
    result = []
    for index, check in enumerate(plan.checks):
        if not isinstance(check, PeelReward):
            continue
        source = observed.get((check.map_name, check.lock_id))
        if source is None or check.hooks != source.variants:
            raise ValueError("Peel check does not match one complete native source and its variants")
        result.append((index, check, source))
    return tuple(result)


def suppress_peel_grants(document: KdmDocument, plan: DeliveryPlan) -> bytes:
    sources = resolve_peels(document, plan)
    targets = {variant.lock_id for _, check, _ in sources for variant in check.hooks}
    edits = {
        record(row, 72)[57].offset: ""
        for array in document.arrays.values()
        if array.type_id == 21
        for row in array.values
        if text(record(row, 72)[0]) in targets
    }
    if len(edits) != len(targets):
        raise ValueError("Peel grant fields are missing or duplicated")
    # Native pickup locks already use null reward pointers (the Luigi records).
    # Leave accepted inputs, paired restoration locks, flags and effects intact.
    return document.edit_strings(edits)


def hook_peel_callback(source: str, index: int, check: PeelReward, observed: PeelSource) -> str:
    # The picker reserves the exact variant before the animation. The native
    # current-target pointer can change during that animation; use the stored
    # selection rather than querying it again from the after callback.
    body = f"\trando_peel_collect_selected*({index});\n"
    source = prepend_body(source, observed.callback, body)
    return prepend_body(source, observed.cancel_callback, f"\trando_peel_cancel*({index});\n")


def peel_variants(plan: DeliveryPlan) -> tuple[tuple[int, int, PeelReward, PeelVariant], ...]:
    result: list[tuple[int, int, PeelReward, PeelVariant]] = []
    for index, check in enumerate(plan.checks):
        if isinstance(check, PeelReward):
            for variant in check.hooks:
                result.append((len(result) + 1, index, check, variant))
    if len(result) > 255:
        raise ValueError("Peel return selectors exceed native byte storage")
    return tuple(result)


def gate_peel_selection(source: str, plan: DeliveryPlan, document: KdmDocument | None = None) -> str:
    import re

    entries = peel_variants(plan)
    pattern = r"\bdecal_dokodemo_mario_control_main\*?\(\)"
    if len(re.findall(pattern, source)) not in (1, 3):
        raise ValueError("Paperization selection no longer matches the inspected revision")
    source = re.sub(pattern, "rando_peel_control*()", source)
    lines = [
        "private rando_peel_control() {",
        "\tlocal localVar0 = decal_dokodemo_mario_control_main*();",
        "\tlocal localVar1 = pepalyze_get_mode*();",
        "\tif ( localVar0 != pepalyze_pickup || localVar1 != pepalyze_mode_pickup ) {\n\t\treturn* localVar0;\n\t}",
        "\tlocal localVar2 = pepalyze_get_now_play_unlock_num*();",
        "\tlocal localVar3 = pouch_get_map_name*();",
        "\tlocal localVar4;",
    ]
    for selector, _, check, variant in entries:
        lines.extend(
            [
                f'\tif ( localVar3 == "{check.map_name}" ) {{',
                f'\t\tlocalVar4 = pepalyze_get_access_number*("{variant.lock_id}");',
                "\t\tif ( localVar2 == localVar4 ) {",
                f"\t\t\tlocalVar4 = rando_peel_can_return*({selector});",
                "\t\t\tif ( localVar4 == false ) {\n\t\t\t\treturn* pepalyze_pickup_miss;\n\t\t\t}",
                "\t\t\treturn* localVar0;\n\t\t}\n\t}",
            ]
        )
    configured = {variant.lock_id for _, _, _, variant in entries}
    configured_rooms = {check.map_name for _, _, check, _ in entries}
    # Luigi and omitted native sources can share a room with randomized scraps.
    # Their original selection must remain usable. Unknown identities still fail
    # closed, since a failed target query must not bypass capacity reservation.
    if document is not None:
        for lock in paperization_locks(document):
            if lock.id in configured or lock.map_name not in configured_rooms:
                continue
            lines.extend(
                [
                    f'\tif ( localVar3 == "{lock.map_name}" ) {{',
                    f'\t\tlocalVar4 = pepalyze_get_access_number*("{lock.id}");',
                    "\t\tif ( localVar2 == localVar4 ) {\n\t\t\treturn* localVar0;\n\t\t}\n\t}",
                ]
            )
    rooms = " || ".join(f'localVar3 == "{name}"' for name in sorted(configured_rooms))
    lines.extend([f"\tif ( {rooms} ) {{\n\t\treturn* pepalyze_pickup_miss;\n\t}}", "\treturn* localVar0;", "}"])
    return source + "\n" + "\n".join(lines) + "\n"


def peel_runtime(plan: DeliveryPlan) -> str:
    entries = peel_variants(plan)
    if not entries:
        return ""
    lines = [
        "public rando_peel_can_return(temp tempVar0) {",
        "\tlocal localVar0 = tempVar0;",
        "\tlocal localVar1 = rando_seed_valid*();",
        "\tif ( localVar1 == false || rando_peel_reserve != 0 ) {\n\t\treturn* false;\n\t}",
    ]
    for selector, index, _, variant in entries:
        checked, _ = plan.receipt(index)
        lines.extend(
            [
                f"\tif ( localVar0 == {selector} ) {{",
                f"\t\tif ( {checked} == false ) {{\n\t\t\trando_peel_reserve = - {selector};\n\t\t\treturn* true;\n\t\t}}",
                "\t\tif ( gs_rando_peel_pending != 0 ) {\n\t\t\treturn* false;\n\t\t}",
                f'\t\tlocalVar1 = item_try_addpouch*("{variant.source_item}", false);',
                f"\t\tif ( localVar1 ) {{\n\t\t\trando_peel_reserve = {selector};\n\t\t}}",
                "\t\treturn* localVar1;\n\t}",
            ]
        )
    lines.extend(
        [
            "\treturn* false;",
            "}",
            "public rando_peel_return_pending() {",
            "\tif ( rando_peel_reserve != 0 ) {\n\t\treturn* false;\n\t}",
            "\tif ( gs_rando_peel_pending == 0 ) {\n\t\treturn* true;\n\t}",
            "\tlocal localVar0;",
        ]
    )
    for selector, _, _, variant in entries:
        lines.extend(
            [
                f"\tif ( gs_rando_peel_pending == {selector} ) {{",
                f'\t\tlocalVar0 = rando_item_grant*("{variant.source_item}");',
                "\t\tif ( localVar0 ) {\n\t\t\tgs_rando_peel_pending *= 0;\n\t\t}",
                "\t\treturn* true;\n\t}",
            ]
        )
    lines.extend(["\treturn* false;", "}", "public rando_peel_cancel(temp tempVar0) {", "\tlocal localVar0 = tempVar0;"])
    for selector, index, _, _ in entries:
        lines.append(
            "\tif ( localVar0 == "
            f"{index}"
            " && ( rando_peel_reserve == "
            f"{selector}"
            " || rando_peel_reserve == - "
            f"{selector}"
            " ) ) {\n\t\trando_peel_reserve = 0;\n\t}"
        )
    lines.extend(
        [
            "}",
            "public rando_peel_collect(temp tempVar0, temp tempVar1) {",
            "\tlocal localVar0 = tempVar0;",
            "\tlocal localVar1 = tempVar1;",
            "\tlocal localVar2 = rando_seed_valid*();",
            "\tif ( localVar2 == false ) {\n\t\treturn*;\n\t}",
        ]
    )
    for selector, index, _, variant in entries:
        checked, _ = plan.receipt(index)
        lines.extend(
            [
                f'\tif ( localVar0 == {index} && localVar1 == "{variant.source_item}" ) {{',
                f"\t\tif ( {checked} == false && rando_peel_reserve == - {selector} ) {{",
                f"\t\t\t{checked} *= true;\n\t\t\trando_peel_reserve = 0;\n\t\t\trando_deliver*();",
                f"\t\t}} else if ( {checked} && rando_peel_reserve == {selector} ) {{",
                "\t\t\tgs_rando_peel_pending *= "
                f"{selector}"
                ";\n\t\t\trando_peel_reserve = 0;\n\t\t\trando_peel_return_pendi"
                "ng*();",
                "\t\t}\n\t\treturn*;\n\t}",
            ]
        )
    lines.extend(["}", "public rando_peel_collect_selected(temp tempVar0) {", "\tlocal localVar0 = tempVar0;"])
    for selector, index, _, variant in entries:
        lines.extend(
            [
                "\tif ( localVar0 == "
                f"{index}"
                " && ( rando_peel_reserve == "
                f"{selector}"
                " || rando_peel_reserve == - "
                f"{selector}"
                " ) ) {",
                f'\t\trando_peel_collect*({index}, "{variant.source_item}");',
                "\t\treturn*;\n\t}",
            ]
        )
    lines.append("}")
    return "\n".join(lines) + "\n"
