"""Compatibility imports for the original version-1 catalog API."""

from .legacy.catalog import (
    CHECK_KINDS,
    KINDS,
    JsonObject,
    Settings,
    requirement_items,
    requirement_met,
    validate_catalog,
)
from .legacy.generation import enabled_checks, generate, playthrough
from .legacy.rewards import RewardState

__all__ = [
    "CHECK_KINDS",
    "KINDS",
    "JsonObject",
    "Settings",
    "requirement_items",
    "requirement_met",
    "validate_catalog",
    "enabled_checks",
    "generate",
    "playthrough",
    "RewardState",
]
