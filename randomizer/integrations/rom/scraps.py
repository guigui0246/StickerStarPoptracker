"""Resolve field scrap objects to the actual key items used by puzzles."""

from dataclasses import dataclass
import re

from .kdm import KdmDocument
from .native_delivery import NativeReward, NativeRewardKind
from .pickups import record, text


@dataclass(frozen=True)
class ScrapItem:
    field_item: str
    inventory_item: str

    @property
    def reward(self) -> NativeReward:
        return NativeReward(NativeRewardKind.ITEM, self.inventory_item)


def scrap_items(document: KdmDocument) -> tuple[ScrapItem, ...]:
    schema = document.structures.get(29)
    if schema is None or schema.fields != (3, 15, 3, 0):
        raise ValueError("Unsupported field-to-inventory item schema")
    inventory = {text(record(row, 19)[0]) for array in document.arrays.values()
                 if array.type_id == 30 for row in array.values}
    result: dict[str, ScrapItem] = {}
    for array in document.arrays.values():
        if array.type_id != 29:
            continue
        for row in array.values:
            fields = record(row, 4)
            field_item = text(fields[0])
            if not field_item.startswith("PK_FIELD_"):
                continue
            item = ScrapItem(field_item, text(fields[2]))
            if not item.inventory_item.startswith("PK_") or item.inventory_item.startswith("PK_FIELD_") or item.inventory_item not in inventory:
                raise ValueError("Field scrap lacks an observed native inventory item")
            if field_item in result:
                raise ValueError("Duplicate field scrap mapping")
            result[field_item] = item
    if not result:
        raise ValueError("No native scrap mappings found")
    return tuple(result[key] for key in sorted(result))


@dataclass(frozen=True)
class ScriptedScrap:
    map_name: str
    object_name: str
    field_item: str


def scripted_scraps(map_name: str, source: str) -> tuple[ScriptedScrap, ...]:
    """Resolve literal and uniquely named static objects; never guess locals."""
    result: dict[tuple[str, str], ScriptedScrap] = {}
    pattern = r'\bitem_static_entry\*?\(([^,\n]+),\s*"(PK_FIELD_[A-Z0-9_]+)"\s*,'
    for match in re.finditer(pattern, source):
        object_expression, item = match.groups()
        object_expression = object_expression.strip()
        scope = source
        literal = re.fullmatch(r'"([a-zA-Z0-9_]+)"', object_expression)
        if literal:
            name = literal[1]
        else:
            if not re.fullmatch(r"(?:var_0x[0-9a-f]+|localVar[0-9]+|tempVar[0-9]+)", object_expression):
                continue
            if object_expression.startswith(("localVar", "tempVar")):
                functions = list(re.finditer(r"^(?:private|public) [^\n]+\{", source, re.MULTILINE))
                preceding = [function for function in functions if function.end() <= match.start()]
                if not preceding:
                    continue
                following = [function.start() for function in functions if function.start() > match.start()]
                scope = source[preceding[-1].end():min(following, default=len(source))]
            names = set(re.findall(r'\b' + re.escape(object_expression) + r'\s*\*?=\s*"([a-zA-Z0-9_]+)"\s*;', scope))
            if len(names) != 1:
                continue
            name = names.pop()
        # Story props such as mp_dummy are explicitly noncollectible.
        flags = re.findall(r'\bitem_set_flg\*?\(\s*' + re.escape(object_expression)
                           + r'\s*,\s*item_flg_no_get\s*,\s*(true|false)\s*\)', scope)
        manual_get = re.search(r'\bitem_get_item_id\*?\(\s*' + re.escape(object_expression) + r'\s*\)', source)
        callbacks = re.findall(r'\bitem_set_itemget_event\*?\(\s*' + re.escape(object_expression) + r'\s*,\s*"([a-zA-Z0-9_]+)"\s*\)', scope)
        callback_get = False
        for callback in callbacks:
            body = re.search(r"^(?:private|public) " + re.escape(callback) + r"\([^\n]*\)[^\n]*\{(.*?)(?=^(?:private|public) |\Z)", source, re.MULTILINE | re.DOTALL)
            callback_get |= body is not None and bool(re.search(r"\bitem_get_evt_piece\*?\(", body[1]))
        if "true" in flags and "false" not in flags and not manual_get and not callback_get:
            continue
        key = (name, item)
        result[key] = ScriptedScrap(map_name, name, item)
    return tuple(result[key] for key in sorted(result))


@dataclass(frozen=True)
class ScrapInventoryAudit:
    inventory_items: tuple[str, ...]
    field_rewards: tuple[str, ...]
    peeled_rewards: tuple[str, ...]
    restoration_inputs: tuple[tuple[str, str], ...]
    story_inputs: tuple[str, ...]
    unclassified: tuple[str, ...]


def audit_scrap_inventory(items: KdmDocument, puzzles: KdmDocument) -> ScrapInventoryAudit:
    """Account for inventory descriptors without inventing pickup locations.

    An accepted input differing from its peel reward is evidence of a native
    restoration transformation, not an additional check or a logic alias.
    Wiggler story inputs remain explicit until their acquisition is verified.
    """
    from .paperization import paperization_locks
    from .peels import peel_sources
    from .pickups import integer
    inventory = {text(record(row, 19)[0]) for array in items.arrays.values()
                 if array.type_id == 30 for row in array.values
                 if integer(record(row, 19)[18]) == 3 and text(record(row, 19)[0]).startswith("PK_")
                 and not text(record(row, 19)[0]).startswith("PK_FIELD_")}
    field = {entry.inventory_item for entry in scrap_items(items)}
    peels = {variant.source_item for source in peel_sources(puzzles) for variant in source.variants}
    if (field | peels) - inventory:
        raise ValueError("Native scrap sources reference missing inventory descriptors")
    locks = paperization_locks(puzzles)
    transformed = {(lock.key_item, accepted) for lock in locks if lock.key_item in peels
                   for accepted in lock.accepted_items if accepted in inventory - field - peels}
    story = {accepted for lock in locks for accepted in lock.accepted_items
             if re.fullmatch(r"PK_HANACHAN_BODY_[1-4]", accepted)}
    if story - inventory:
        raise ValueError("Wiggler puzzles reference missing native inventory descriptors")
    classified = field | peels | {accepted for _, accepted in transformed} | story
    return ScrapInventoryAudit(tuple(sorted(inventory)), tuple(sorted(field)), tuple(sorted(peels)),
                               tuple(sorted(transformed)), tuple(sorted(story)), tuple(sorted(inventory - classified)))
