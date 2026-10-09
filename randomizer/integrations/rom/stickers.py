"""ROM-derived sticker unlocks, copy conversion and shop inventories."""

from dataclasses import dataclass
import struct
import re

from .kdm import KdmDocument, KdmPointer
from .pickups import integer, record, text


@dataclass(frozen=True)
class StickerPolicy:
    generic: tuple[str, ...]
    things: tuple[tuple[str, str], ...]
    replacement: str = "SL_W6_SANDAL_S"

    def __post_init__(self) -> None:
        ids = self.generic + tuple(sticker for sticker, _ in self.things)
        if not ids or len(set(ids)) != len(ids) or self.replacement not in self.generic:
            raise ValueError("Sticker policy requires distinct ROM-derived items and flip-flops")
        if any(not isinstance(item, str) or not re.fullmatch(r"SL_[A-Z0-9_]+", item) for item in ids) or any(
            real != "REAL_" + item[3:] for item, real in self.things
        ):
            raise ValueError("Invalid sticker and Thing identities")

    @property
    def flags(self) -> tuple[str, ...]:
        return tuple(self.flag(item) for item in self.generic)

    def flag(self, item: str) -> str:
        if item not in self.generic:
            raise ValueError("Unknown generic sticker")
        return "gf_rando_unlock_" + item.lower()

    def grant(self, item: str, *, unlock: bool, result: str) -> list[str]:
        if item in self.generic:
            flag = self.flag(item)
            if unlock:
                # Ownership authorizes the global native insertion guard. The
                # copy receipt still waits for space and retries after failure.
                return [f"{flag} *= true;", f'{result} = rando_item_grant*("{item}");']
            return [
                f"if ( {flag} ) {{",
                f'\t{result} = rando_item_grant*("{item}");',
                "} else {",
                f'\t{result} = rando_item_grant*("{self.replacement}");',
                "}",
            ]
        thing = dict(self.things).get(item)
        if thing is None:
            raise ValueError("Reward is not a recognized sticker")
        lines = [f'{result} = rando_item_grant*("{item}");']
        if unlock:
            lines.append(f'if ( {result} ) {{\n\tpouch_already_get_real_item_debug*("{thing}");\n}}')
        return lines

    def pickup_functions(self) -> str:
        lines = [
            "public rando_sticker_init()  {",
            "\titem_set_flg*(self, item_flg_add_pouch, false);",
            '\titem_set_itemget_event*(self, "rando_sticker_get");',
            "}",
            "public rando_sticker_get()  {",
            "\ttemp tempVar0 = rando_seed_valid*();",
            "\tif ( tempVar0 == false ) {\n\t\treturn*;\n\t}",
            "\ttemp tempVar1 = item_get_item_id*(self);",
            "\ttempVar0 = false;",
        ]
        for item in self.generic:
            lines.append(f'\tif ( tempVar1 == "{item}" ) {{')
            lines.extend("\t\t" + line.replace("\n", "\n\t\t") for line in self.grant(item, unlock=False, result="tempVar0"))
            lines.append("\t}")
        lines.extend(["\tif ( tempVar0 ) {", "\t\tcharacter_hide*(self);", "\t\titem_delete*(self, 0);", "\t}", "}"])
        return "\n".join(lines) + "\n"


def sticker_policy(data: bytes) -> StickerPolicy:
    document = KdmDocument(data)
    rows = [record(row, 19) for array in document.arrays.values() if array.type_id == 30 for row in array.values]
    real = {text(row[0]) for row in rows if text(row[0]).startswith("REAL_")}
    stickers = sorted({text(row[0]) for row in rows if integer(row[18]) == 4 and text(row[0]).startswith("SL_")})
    things = tuple((item, "REAL_" + item[3:]) for item in stickers if "REAL_" + item[3:] in real)
    thing_ids = {item for item, _ in things}
    return StickerPolicy(tuple(item for item in stickers if item not in thing_ids), things)


def patch_sticker_initializers(data: bytes, policy: StickerPolicy) -> bytes:
    document = KdmDocument(KdmDocument(data).add_strings(("rando_sticker_init",)))
    edits: dict[int, str] = {}
    for array in document.arrays.values():
        if array.type_id != 30:
            continue
        for row in array.values:
            fields = record(row, 19)
            if text(fields[0]) in policy.generic:
                if text(fields[15]) or text(fields[16]):
                    raise ValueError("Sticker already has a custom callback; compose it explicitly")
                edits[fields[15].offset] = "rando_sticker_init"
    if len(edits) != len(policy.generic):
        raise ValueError("Sticker definitions are missing or duplicated")
    return document.edit_strings(edits)


def patch_shops(data: bytes, policy: StickerPolicy) -> bytes:
    """Expand every generic shop with gated entries; retain the Thing shop intact.

    Builds pointer tables from validated source records. Record values other than
    the item and unlock condition retain the original ordinary-shop defaults.
    """
    document = KdmDocument(KdmDocument(data).add_strings(policy.generic + policy.flags))
    if document.structures[21].fields != (3, 3, 8, 3, 13):
        raise ValueError("Unsupported shop record schema")
    shops = {"SHOP_TOWN", "SHOP_IWA", "SHOP_DOR", "SHOP_SNOW", "SHOP_KAZAN", "SHOP_KOOPA"}
    if not shops <= document.tables.keys():
        raise ValueError("Missing generic shop tables")
    # This revision stores shop records solely in the data section, and named
    # tables contain pointers to those records. Reject more complex layouts.
    if any(
        array.type_id != 21 or len(array.values) != 1
        for array in document.arrays.values()
        if array.address < document.sections[6]
    ):
        raise ValueError("Unexpected shop data layout")
    if any(table.type_id != 15 for table in document.tables.values()):
        raise ValueError("Expected shop pointer tables")
    strings = {value: address for address, value in document.strings.items()}
    strings[""] = 0
    records = bytearray()
    addresses: list[int] = []
    array_ids = {array.id for array in document.arrays.values()}
    next_id = max(array_ids) + 1
    for item in policy.generic:
        if next_id > 65535:
            raise ValueError("Shop array ID exceeds native capacity")
        addresses.append(document.sections[6] + len(records) + 8)
        records.extend(struct.pack("<4H", next_id, 5, 21, 5))
        records.extend(struct.pack("<IIH2xII", strings[item], strings[policy.flag(item)], 0, 0, 0))
        next_id += 1
    # Keep the original sentinel (null pointer) as the final entry.
    tables = bytearray(document.data[document.sections[6] : document.sections[6] + 4 + 4 * len(document.tables)])
    for name, table in document.tables.items():
        values = (
            addresses + [0]
            if name in shops
            else [field.value.address for field in table.values if isinstance(field.value, KdmPointer)]
        )
        if len(values) != len(table.values) and name not in shops:
            raise ValueError("Unexpected non-pointer shop entry")
        if name in shops and (
            not table.values or not isinstance(table.values[-1].value, KdmPointer) or table.values[-1].value.address
        ):
            raise ValueError("Expected null shop sentinel")
        tables.extend(struct.pack("<4H", table.id, len(values), 15, len(values)))
        tables.extend(struct.pack(f"<{len(values)}I", *values))
    result = bytearray(document.data[: document.sections[6]] + records + tables + document.data[document.sections[7] :])
    struct.pack_into("<I", result, document.sections[5], document.u32(document.sections[5]) + len(addresses))
    struct.pack_into("<I", result, 8 + 6 * 4, (document.sections[6] + len(records)) // 4)
    struct.pack_into("<I", result, 8 + 7 * 4, (document.sections[6] + len(records) + len(tables)) // 4)
    rebuilt = KdmDocument(bytes(result))
    for name in shops:
        actual = []
        for field in rebuilt.tables[name].values[:-1]:
            if not isinstance(field.value, KdmPointer):
                raise ValueError("Shop relocation failed")
            row = record(rebuilt.pointed_array(field.value).values[0], 5)
            actual.append((text(row[0]), text(row[1])))
        if actual != [(item, policy.flag(item)) for item in policy.generic]:
            raise ValueError("Expanded shop contents failed verification")
    return bytes(result)
