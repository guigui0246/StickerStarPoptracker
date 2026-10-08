"""Regions and bidirectional paths with independent directional requirements."""

from dataclasses import dataclass
from .rules import Rules


@dataclass(frozen=True)
class Region:
    id: str
    name: str


@dataclass(frozen=True)
class StartingRegion(Region):
    """The sole unconditional starting region: the menu/world map."""


@dataclass(frozen=True)
class Vector:
    source: str
    target: str
    rules: Rules = Rules()


@dataclass(frozen=True)
class Path:
    id: str
    forward: Vector
    reverse: Vector

    def __post_init__(self) -> None:
        if (self.forward.source, self.forward.target) != (
            self.reverse.target,
            self.reverse.source,
        ):
            raise ValueError("A path must have two opposing vectors")
        if self.forward.source == self.forward.target:
            raise ValueError("A path must connect distinct regions")
