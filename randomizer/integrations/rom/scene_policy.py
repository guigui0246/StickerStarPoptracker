"""Explicit, asset-free scene entry/cleanup bindings for presentation authors."""

from dataclasses import dataclass
import re

from .script_build import replace_body


@dataclass(frozen=True)
class SceneSkip:
    script_file: str
    entry: str
    cleanup: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"Script/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.bin", self.script_file):
            raise ValueError("Scene skip must name an existing script path")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (self.entry, self.cleanup)):
            raise ValueError("Scene callbacks require ordinary function names")
        if self.entry == self.cleanup or any(name.startswith("rando_") for name in (self.entry, self.cleanup)):
            raise ValueError("Scene skips require distinct original entry and cleanup callbacks")


def skip_scene(source: str, scene: SceneSkip) -> str:
    """Replace a visual timeline with its author's original cleanup callback.

    The callback must be defined here and take no arguments. A gameplay hook
    already injected into the entry cannot be erased. These checks establish
    compiler contracts, not that the selected cleanup performs every required
    story effect; authors must verify that choice in the game.
    """
    entries = []
    for name in (scene.entry, scene.cleanup):
        matches = list(re.finditer(r"\b(?:private|public) " + re.escape(name) + r"\(\s*\)\s*\{", source))
        if len(matches) != 1:
            raise ValueError(f"Scene callback needs one original zero-argument function: {name}")
        entries.append(matches[0])
    start = entries[0].end()
    following = re.search(r"\n(?:private|public) ", source[start:])
    body = source[start : start + following.start()] if following else source[start:]
    if re.search(r"\brando_[A-Za-z0-9_]+", body):
        raise ValueError("Scene skip cannot erase an injected gameplay hook")
    return replace_body(source, scene.entry, f"\t{scene.cleanup}*();\n\treturn*;")
