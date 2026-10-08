"""Read game files from a validated dump and emit isolated LayeredFS overrides."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from .inspection import RomInspection, inspect_rom, read_at


@dataclass
class RomProject:
    source: Path
    inspection: RomInspection = field(init=False)

    def __post_init__(self) -> None:
        self.inspection = inspect_rom(self.source)
        if not self.inspection.decrypted:
            raise ValueError("The dump must contain decrypted game files")
        if self.inspection.title_id != "00040000000A5F00":
            raise ValueError("Only the inspected European title is supported")

    def read_file(self, name: str) -> bytes:
        entry = next(
            (entry for entry in self.inspection.romfs if entry.name == name), None
        )
        if entry is None:
            raise ValueError(f"Unknown RomFS file: {name}")
        with self.source.open("rb") as stream:
            return read_at(stream, entry.offset, entry.size, self.source.stat().st_size)

    def write_override(self, output: Path, name: str, data: bytes) -> Path:
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(
            part in {"..", "."} or ":" in part or "\\" in part
            for part in relative.parts
        ):
            raise ValueError("Unsafe RomFS path")
        if name not in {entry.name for entry in self.inspection.romfs}:
            raise ValueError("Overrides must replace existing game files")
        root = output.resolve()
        target = (root / "romfs" / Path(*relative.parts)).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Override path escapes output folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(
                f"Refusing to overwrite an existing mod file: {target}"
            )
        target.write_bytes(data)
        return target
