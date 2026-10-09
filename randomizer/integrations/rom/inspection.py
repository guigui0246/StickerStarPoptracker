"""Read-only NCSD/NCCH and decrypted RomFS inspection.

No decryption keys, patch offsets, or game data are distributed here.
"""

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import BinaryIO


@dataclass(frozen=True)
class RomFile:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class RomInspection:
    title_id: str
    product_code: str
    decrypted: bool
    exefs: tuple[RomFile, ...]
    romfs: tuple[RomFile, ...]


def read_at(stream: BinaryIO, offset: int, size: int, limit: int) -> bytes:
    if offset < 0 or size < 0 or offset + size > limit:
        raise ValueError("ROM range exceeds file bounds")
    stream.seek(offset)
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Truncated ROM")
    return data


def inspect_rom(path: Path) -> RomInspection:
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = read_at(stream, 0, 512, size)
        if header[256:260] != b"NCSD":
            raise ValueError("Expected a .3ds NCSD container")
        partition = int.from_bytes(header[288:292], "little") * 512
        ncch = read_at(stream, partition, 512, size)
        if ncch[256:260] != b"NCCH":
            raise ValueError("Primary partition is not NCCH")
        title = ncch[280:288][::-1].hex().upper()
        product = ncch[336:352].split(b"\0")[0].decode("ascii")
        exefs_base = partition + int.from_bytes(ncch[416:420], "little") * 512
        exefs_header = read_at(stream, exefs_base, 512, size)
        romfs_base = partition + int.from_bytes(ncch[432:436], "little") * 512
        ivfc = read_at(stream, romfs_base, 96, size)
        if ivfc[:4] != b"IVFC" or exefs_header[:8].rstrip(b"\0") != b".code":
            return RomInspection(title, product, False, (), ())
        exefs: list[RomFile] = []
        for index in range(10):
            entry = exefs_header[index * 16 : index * 16 + 16]
            name = entry[:8].split(b"\0")[0].decode("ascii")
            if name:
                offset, length = struct.unpack("<II", entry[8:])
                absolute = exefs_base + 512 + offset
                if absolute + length > size:
                    raise ValueError("Invalid ExeFS entry")
                exefs.append(RomFile(name, absolute, length))
        # The physical level-3 block starts after the IVFC header/master hashes.
        exponent = int.from_bytes(ivfc[76:80], "little")
        if not 9 <= exponent <= 20:
            raise ValueError("Unsupported IVFC block size")
        block_size = 1 << exponent
        master_size = int.from_bytes(ivfc[8:12], "little")
        level3 = romfs_base + ((96 + master_size + block_size - 1) // block_size) * block_size
        layout = struct.unpack("<10I", read_at(stream, level3, 40, size))
        if layout[0] != 40:
            raise ValueError("Unsupported RomFS level-3 header")
        directories = read_at(stream, level3 + layout[3], layout[4], size)
        files = read_at(stream, level3 + layout[7], layout[8], size)
        data_base = level3 + layout[9]
        result: list[RomFile] = []
        seen_dirs: set[int] = set()
        seen_files: set[int] = set()
        absent = 0xFFFFFFFF

        def visit(offset: int, parent: str) -> None:
            if offset in seen_dirs or offset + 24 > len(directories):
                raise ValueError("Invalid or cyclic RomFS directory table")
            seen_dirs.add(offset)
            _, _, child, file_offset, _, name_size = struct.unpack_from("<6I", directories, offset)
            if offset + 24 + name_size > len(directories):
                raise ValueError("Truncated directory name")
            name = directories[offset + 24 : offset + 24 + name_size].decode("utf-16-le")
            current = f"{parent}/{name}".strip("/")
            while file_offset != absent:
                if file_offset in seen_files or file_offset + 32 > len(files):
                    raise ValueError("Invalid or cyclic RomFS file table")
                seen_files.add(file_offset)
                _, sibling, relative, length, _, name_size = struct.unpack_from("<IIQQII", files, file_offset)
                if file_offset + 32 + name_size > len(files):
                    raise ValueError("Truncated file name")
                name = files[file_offset + 32 : file_offset + 32 + name_size].decode("utf-16-le")
                absolute = data_base + relative
                if absolute + length > size:
                    raise ValueError("Invalid RomFS data range")
                result.append(RomFile(f"{current}/{name}".lstrip("/"), absolute, length))
                file_offset = sibling
            while child != absent:
                if child + 24 > len(directories):
                    raise ValueError("Invalid child directory")
                sibling = struct.unpack_from("<I", directories, child + 4)[0]
                visit(child, current)
                child = sibling

        visit(0, "")
        return RomInspection(title, product, True, tuple(exefs), tuple(result))
