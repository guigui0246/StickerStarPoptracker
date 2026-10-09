"""Exact native treasure-file contents and their shared acquisition callback."""

from dataclasses import dataclass
import re

from .kdm import KdmDocument
from .native_delivery import DeliveryPlan, ContainerReward
from .pickups import integer, pointer, record, text
from .script_build import prepend_body

TREASURE_SCRIPT = "Script/Mobj/ksm_treasure_file.bin"


@dataclass(frozen=True)
class ContainerSource:
    group_name: str
    map_name: str
    object_name: str
    container_type: str
    source_item: str
    collection_flag: int
    item_field_offset: int


def container_sources(document: KdmDocument) -> tuple[ContainerSource, ...]:
    expected = {21: (3, 3), 22: (3, 15, 1), 23: (1, 15), 24: (15, 15, 1, 1),
                29: (3, 1, 1, 1, 15, 15),
                36: (3, 3, 3, 0, 0, 0, 0, 4, 1, 1, 15, 15),
                38: (3, 15, 1), 42: (3, 20, 1, 20, 1, 20, 1, 20, 1, 15)}
    if any(identifier not in document.structures or document.structures[identifier].fields != fields
           for identifier, fields in expected.items()):
        raise ValueError("Unsupported native container disposition schema")
    result: dict[tuple[str, str], ContainerSource] = {}
    for reference in document.tables["all_disposDataTbl"].values:
        group_pointer = pointer(reference)
        if not group_pointer.address:
            continue
        for group in document.pointed_array(group_pointer).values:
            group_fields = record(group, 10)
            maps = pointer(group_fields[5])
            if not maps.address:
                continue
            for map_reference in document.pointed_array(maps).values:
                map_pointer = pointer(map_reference)
                if not map_pointer.address:
                    continue
                for map_record in document.pointed_array(map_pointer).values:
                    map_fields = record(map_record, 3)
                    objects = pointer(map_fields[1])
                    if not objects.address:
                        continue
                    object_array = document.pointed_array(objects)
                    if object_array.type_id != 36 or integer(map_fields[2]) != len(object_array.values):
                        raise ValueError("Native container object count does not match its map")
                    for obj in object_array.values:
                        fields = record(obj, 12)
                        if text(fields[1]) != "TREASURE_FILE":
                            continue
                        definition_pointer = pointer(fields[10])
                        if not definition_pointer.address:
                            continue  # The empty story chest has no native item definition.
                        definition = document.pointed_array(definition_pointer)
                        if definition.type_id != 29 or len(definition.values) != 1:
                            raise ValueError("Treasure file lacks one native object definition")
                        parameters = pointer(record(definition.values[0], 6)[4])
                        if not parameters.address:
                            continue  # An observed empty story chest has no loot definition.
                        parameter_array = document.pointed_array(parameters)
                        if parameter_array.type_id != 24 or len(parameter_array.values) != 1:
                            raise ValueError("Unsupported treasure-file loot parameters")
                        loot = record(parameter_array.values[0], 4)
                        if pointer(loot[1]).address:
                            fallback = document.pointed_array(pointer(loot[1]))
                            if fallback.type_id != 23 or len(fallback.values) != integer(loot[2]):
                                raise ValueError("Unsupported treasure fallback list")
                            for weighted in fallback.values:
                                fallback_fields = record(weighted, 2)
                                fallback_list = document.pointed_array(pointer(fallback_fields[1]))
                                if fallback_list.type_id != 22 or len(fallback_list.values) != 1:
                                    raise ValueError("Unsupported treasure fallback reward")
                                fallback_contents = document.pointed_array(pointer(record(fallback_list.values[0], 3)[1]))
                                if fallback_contents.type_id != 21 or any(text(record(entry, 2)[0]).startswith(("PK_", "REAL_")) for entry in fallback_contents.values):
                                    raise ValueError("Treasure fallback contains another progression source")
                        list_pointer = pointer(loot[0])
                        if not list_pointer.address:
                            continue
                        lists = document.pointed_array(list_pointer)
                        if lists.type_id != 22 or len(lists.values) != 1:
                            raise ValueError("Treasure file must have one named loot list")
                        list_fields = record(lists.values[0], 3)
                        contents = document.pointed_array(pointer(list_fields[1]))
                        if contents.type_id != 21 or len(contents.values) != 1 or integer(list_fields[2]) != 1:
                            raise ValueError("Treasure file must have one deterministic native reward")
                        item = record(contents.values[0], 2)[0]
                        source = ContainerSource(text(group_fields[0]), text(map_fields[0]), text(fields[0]),
                                                 text(fields[1]), text(item), integer(fields[8]), item.offset)
                        identity = source.map_name, source.object_name
                        if identity in result:
                            raise ValueError("Duplicate native container identity")
                        result[identity] = source
    return tuple(result[identity] for identity in sorted(result))


def container_runtime(plan: DeliveryPlan) -> str:
    checks = [(index, check) for index, check in enumerate(plan.checks) if isinstance(check, ContainerReward)]
    if not checks:
        return ""
    lines = ["public rando_container_collect(temp tempVar0, temp tempVar1) {",
             "\tlocal localVar0 = tempVar0;", "\tlocal localVar1 = tempVar1;",
             "\tlocal localVar2 = pouch_get_map_name*();", "\tlocal localVar3;"]
    for index, check in checks:
        checked, _ = plan.receipt(index)
        lines.extend([f'\tif ( localVar2 == "{check.map_name}" && localVar0 == "{check.object_name}" && localVar1 == "{check.source_item}" ) {{',
                      "\t\tlocalVar3 = rando_seed_valid*();",
                      "\t\tif ( localVar3 == false ) {\n\t\t\treturn* -1;\n\t\t}",
                      f"\t\t{checked} *= true;", "\t\trando_deliver*();", "\t\treturn* true;\n\t}"])
    return "\n".join(lines + ["\treturn* false;", "}"]) + "\n"


def hook_treasure_acquisition(source: str) -> str:
    body = ('\tlocal localVar90 = character_get_name*();\n'
            '\tlocal localVar91 = mobj_get_item_name*(self);\n'
            '\tlocal localVar92 = rando_container_collect*(localVar90, localVar91);\n'
            '\tif ( localVar92 == -1 ) {\n\t\treturn*;\n\t}\n')
    source = prepend_body(source, "action", body)
    for name, arguments in (("item_try_addpouch", "tempVar8"),
                            ("item_try_addpouch", "tempVar8, true"),
                            ("item_disp_get_ui", "tempVar8, true, true, 60")):
        pattern = r"\t" + name + r"\*?\(" + re.escape(arguments) + r"\);"
        if len(re.findall(pattern, source)) != 1:
            raise ValueError("Treasure acquisition no longer matches the inspected native callback")
        source = re.sub(pattern, lambda match: "\tif ( localVar92 == false ) {\n\t" + match[0] + "\n\t}", source)
    return source
