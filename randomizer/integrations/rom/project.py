"""Read game files from a validated dump and emit isolated LayeredFS overrides."""

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import struct
import time
from .inspection import RomInspection, inspect_rom, read_at


def publish_directory(source: Path, target: Path) -> None:
    """Publish atomically, tolerating a brief Windows scanner rename lock."""
    for attempt in range(6):
        if target.exists() or target.is_symlink():
            raise FileExistsError("Output appeared while building; existing files are preserved")
        try:
            source.rename(target)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) != 5 or attempt == 5:
                raise
            time.sleep(0.05 * (2**attempt))


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
        entry = next((entry for entry in self.inspection.romfs if entry.name == name), None)
        if entry is None:
            raise ValueError(f"Unknown RomFS file: {name}")
        with self.source.open("rb") as stream:
            return read_at(stream, entry.offset, entry.size, self.source.stat().st_size)

    def read_exefs(self, name: str) -> bytes:
        matches = [entry for entry in self.inspection.exefs if entry.name == name]
        if len(matches) != 1:
            raise ValueError("Unknown or ambiguous executable file")
        entry = matches[0]
        with self.source.open("rb") as stream:
            return read_at(stream, entry.offset, entry.size, self.source.stat().st_size)

    def codeset_layout(self) -> tuple[tuple[int, int, int], ...]:
        """Read executable segment bounds from the primary NCCH exheader."""
        size = self.source.stat().st_size
        with self.source.open("rb") as stream:
            header = read_at(stream, 0, 512, size)
            partition = int.from_bytes(header[288:292], "little") * 512
            exheader = read_at(stream, partition + 512, 64, size)
        return tuple(struct.unpack_from("<III", exheader, offset) for offset in (16, 32, 48))

    def write_override(self, output: Path, name: str, data: bytes) -> Path:
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(part in {"..", "."} or ":" in part or "\\" in part for part in relative.parts):
            raise ValueError("Unsafe RomFS path")
        if name not in {entry.name for entry in self.inspection.romfs}:
            raise ValueError("Overrides must replace existing game files")
        root = output.resolve()
        target = (root / "romfs" / Path(*relative.parts)).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Override path escapes output folder")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite an existing mod file: {target}")
        target.write_bytes(data)
        return target
