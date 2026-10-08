"""Rewards and fixed, local event tokens."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    progression: bool = True


@dataclass(frozen=True)
class Event(Item):
    """A local token granted only at its declared location, never shuffled."""

    location_id: str = ""
