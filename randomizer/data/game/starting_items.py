"""Typed starting items selection; use Item constants from items.py."""

from ...domain import Item
from . import items


STARTING_ITEMS: tuple[Item, ...] = (
    items.ABILITY_HAMMER,
    items.ABILITY_PAPERIZATION,
    items.STAGE_ACCESS_A01,
    items.STAGE_ACCESS_X00,
    items.STICKER_COPY_SL_JUMP,
)
