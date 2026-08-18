"""TikTok chunk planning: the rules are unusual and easy to get wrong."""

import pytest

from sau.errors import PlatformError
from sau.platforms.tiktok.publisher import (
    MAX_CHUNK_BYTES,
    MAX_CHUNKS,
    MIN_CHUNK_BYTES,
    iter_ranges,
    plan_chunks,
)

MB = 1024 * 1024


def test_small_file_is_a_single_chunk():
    plan = plan_chunks(2 * MB, preferred_chunk=16 * MB)
    assert plan.total_chunks == 1
    assert plan.chunk_size == 2 * MB


def test_preferred_chunk_is_clamped_to_the_allowed_window():
    assert plan_chunks(500 * MB, preferred_chunk=1 * MB).chunk_size == MIN_CHUNK_BYTES
    assert plan_chunks(5000 * MB, preferred_chunk=256 * MB).chunk_size == MAX_CHUNK_BYTES


def test_chunk_count_never_exceeds_the_limit():
    plan = plan_chunks(40_000 * MB, preferred_chunk=MIN_CHUNK_BYTES)
    assert plan.total_chunks <= MAX_CHUNKS
    assert plan.chunk_size <= MAX_CHUNK_BYTES


def test_oversized_file_is_rejected_rather_than_silently_truncated():
    with pytest.raises(PlatformError):
        plan_chunks(MAX_CHUNK_BYTES * MAX_CHUNKS * 2, preferred_chunk=MAX_CHUNK_BYTES)


def test_ranges_cover_the_file_exactly_with_no_gaps():
    size = 137 * MB
    plan = plan_chunks(size, preferred_chunk=16 * MB)
    ranges = list(iter_ranges(size, plan))

    assert len(ranges) == plan.total_chunks
    assert ranges[0][0] == 0
    assert sum(length for _, length in ranges) == size

    expected_offset = 0
    for offset, length in ranges:
        assert offset == expected_offset
        expected_offset += length


def test_final_chunk_absorbs_the_remainder():
    size = 100 * MB + 3
    plan = plan_chunks(size, preferred_chunk=16 * MB)
    *_, (offset, length) = iter_ranges(size, plan)

    # TikTok requires the remainder to ride along with the last chunk rather
    # than being sent as an extra short one.
    assert offset + length == size
    assert length >= plan.chunk_size


def test_zero_length_is_rejected():
    with pytest.raises(ValueError):
        plan_chunks(0, preferred_chunk=16 * MB)
