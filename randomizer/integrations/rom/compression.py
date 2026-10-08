"""Bounds-checked decoder for the backwards LZSS used by 3DS .code files."""

import struct


def decompress_code(data: bytes, maximum_size: int = 32 * 1024 * 1024) -> bytes:
    if len(data) < 8:
        raise ValueError("Missing compression footer")
    layout, extra = struct.unpack_from("<2I", data, len(data) - 8)
    encoded_size = layout & 0xFFFFFF
    header_size = layout >> 24
    output_size = len(data) + extra
    if not 8 <= header_size <= encoded_size <= len(data) or output_size > maximum_size:
        raise ValueError("Invalid backwards LZSS footer")
    result = bytearray(data) + bytearray(extra)
    cursor = len(data) - header_size
    stop = len(data) - encoded_size
    output = output_size
    while cursor > stop:
        cursor -= 1
        control = data[cursor]
        for bit in range(7, -1, -1):
            if cursor <= stop:
                break
            if control & (1 << bit):
                if cursor - 2 < stop:
                    raise ValueError("Truncated LZSS reference")
                cursor -= 2
                token = int.from_bytes(data[cursor : cursor + 2], "little")
                length = (token >> 12) + 3
                distance = (token & 0xFFF) + 2
                if output - length < stop:
                    raise ValueError("LZSS output underflow")
                for _ in range(length):
                    if output + distance >= output_size:
                        raise ValueError("LZSS reference outside output")
                    value = result[output + distance]
                    output -= 1
                    result[output] = value
            else:
                if output <= stop:
                    raise ValueError("LZSS literal underflow")
                cursor -= 1
                output -= 1
                result[output] = data[cursor]
    if output != stop:
        raise ValueError("LZSS stream does not fill the expected output")
    return bytes(result)
