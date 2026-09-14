"""Encodage compact de la grille et de la progression (cahier des charges §6.1, §6.3).

Une grille de 45 900 cases n'est jamais interrogée case par case : elle est
lue et écrite comme un bloc. Ces fonctions convertissent entre la
représentation Python la plus pratique (liste d'entiers, ensemble d'index
cochés) et le format compact stocké en base / transmis sur le fil.
"""

from __future__ import annotations

import base64
import struct
from collections.abc import Iterable, Sequence

GRID_ENCODING = "uint16le"


def encode_uint16_layer(values: Sequence[int]) -> bytes:
    """Encode une couche de grille en `Uint16Array` little-endian (§6.3).

    Ordre de parcours attendu par l'appelant : ligne par ligne, de gauche à
    droite, de haut en bas — cette fonction ne fait qu'empaqueter les octets.
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
    """Nombre d'octets nécessaires pour un bitmap de `cell_count` cases."""
    return (cell_count + 7) // 8


def empty_bitmap(cell_count: int) -> bytes:
    return bytes(bitmap_byte_length(cell_count))


def bitmap_from_indices(indices: Iterable[int], cell_count: int) -> bytes:
    """Construit un bitmap à partir des index cochés (utilisé par le seed de démonstration)."""
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
