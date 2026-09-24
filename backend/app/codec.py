"""Compact encoding of the grid and of progress (specification §6.1, §6.3).

A 45,900-cell grid is never queried cell by cell: it is read and written as
a block. These functions convert between the most convenient Python
representation (list of integers, set of checked indices) and the compact
format stored in the database / sent over the wire.
"""

from __future__ import annotations

import base64
import struct
from collections.abc import Iterable, Sequence

GRID_ENCODING = "uint16le"


def encode_uint16_layer(values: Sequence[int]) -> bytes:
    """Encode a grid layer as a little-endian `Uint16Array` (§6.3).

    Traversal order expected from the caller: row by row, left to right, top
    to bottom — this function only packs the bytes.
    """
    if not values:
        return b""
    return struct.pack(f"<{len(values)}H", *values)


def decode_uint16_layer(data: bytes) -> list[int]:
    count = len(data) // 2
    if count == 0:
        return []
    return list(struct.unpack(f"<{count}H", data))


def bytes_to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def base64_to_bytes(data: str) -> bytes:
    return base64.b64decode(data)


def bitmap_byte_length(cell_count: int) -> int:
    """Number of bytes needed for a bitmap of `cell_count` cells."""
    return (cell_count + 7) // 8


def empty_bitmap(cell_count: int) -> bytes:
    return bytes(bitmap_byte_length(cell_count))


def bitmap_from_indices(indices: Iterable[int], cell_count: int) -> bytes:
    """Build a bitmap from the checked indices (used by the demo seed)."""
    bitmap = bytearray(bitmap_byte_length(cell_count))
    for index in indices:
        byte_index, bit_index = divmod(index, 8)
        bitmap[byte_index] |= 1 << bit_index
    return bytes(bitmap)


def get_bit(bitmap: bytes, index: int) -> bool:
    byte_index, bit_index = divmod(index, 8)
    if byte_index >= len(bitmap):
        return False
    return bool(bitmap[byte_index] & (1 << bit_index))


def set_bit(bitmap: bytearray, index: int, value: bool) -> None:
    byte_index, bit_index = divmod(index, 8)
    if value:
        bitmap[byte_index] |= 1 << bit_index
    else:
        bitmap[byte_index] &= ~(1 << bit_index) & 0xFF


def count_set_bits(bitmap: bytes) -> int:
    if not bitmap:
        return 0
    return int.from_bytes(bitmap, "little").bit_count()
