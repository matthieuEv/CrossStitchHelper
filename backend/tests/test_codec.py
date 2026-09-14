from __future__ import annotations

from app.codec import (
    bitmap_from_indices,
    count_set_bits,
    decode_uint16_layer,
    encode_uint16_layer,
    get_bit,
    set_bit,
)


def test_uint16_layer_round_trips() -> None:
    values = [0, 1, 65535, 42, 0, 12345]
    assert decode_uint16_layer(encode_uint16_layer(values)) == values


def test_uint16_layer_handles_empty() -> None:
    assert encode_uint16_layer([]) == b""
    assert decode_uint16_layer(b"") == []


def test_bitmap_from_indices_sets_only_given_bits() -> None:
    bitmap = bitmap_from_indices([0, 3, 9], cell_count=17)
    for index in range(17):
        assert get_bit(bitmap, index) == (index in (0, 3, 9))


def test_count_set_bits_matches_indices() -> None:
    bitmap = bitmap_from_indices(range(0, 100, 3), cell_count=100)
    assert count_set_bits(bitmap) == len(range(0, 100, 3))


def test_set_bit_mutates_in_place() -> None:
    bitmap = bytearray(bitmap_from_indices([], cell_count=16))
    set_bit(bitmap, 5, True)
    assert get_bit(bytes(bitmap), 5) is True
    set_bit(bitmap, 5, False)
    assert get_bit(bytes(bitmap), 5) is False
