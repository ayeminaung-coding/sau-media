"""Episode numbers come out of filenames; getting that wrong reorders a series."""

import pytest

from sau.series import (
    SeriesNameError,
    duplicate_parts,
    missing_parts,
    parse_part,
    try_parse_part,
)


class TestParsePart:
    @pytest.mark.parametrize(
        ("filename", "index"),
        [
            ("part1_fileName.mp4", 1),
            ("part2_filename.mp4", 2),
            ("part10_something.mp4", 10),
            ("Part 03 - the reveal.mp4", 3),
            ("PART_7_x.mov", 7),
            ("ep4_x.mp4", 4),
            ("episode.12.finale.mp4", 12),
            ("nested/path/part5_x.mp4", 5),
        ],
    )
    def test_reads_the_number(self, filename, index):
        assert parse_part(filename).index == index

    def test_double_digits_are_not_split(self):
        # The separator after the digits is what stops `part12_x` being read
        # as part 1 — a series that silently renumbers itself is the worst
        # possible failure here.
        assert parse_part("part12_x.mp4").index == 12

    def test_label_is_the_rest_of_the_name(self):
        assert parse_part("part3_the_long_night.mp4").label == "the long night"

    def test_missing_label_is_empty_not_none(self):
        assert parse_part("part3.mp4").label == ""

    @pytest.mark.parametrize(
        "filename",
        ["chapter1_x.mp4", "1_x.mp4", "final.mp4", "partx_1.mp4", ""],
    )
    def test_unparseable_names_raise_rather_than_guess(self, filename):
        with pytest.raises(SeriesNameError):
            parse_part(filename)

    def test_part_zero_is_rejected(self):
        # It would sort ahead of the real first episode.
        with pytest.raises(SeriesNameError):
            parse_part("part0_x.mp4")

    def test_try_parse_returns_none_instead_of_raising(self):
        assert try_parse_part("nope.mp4") is None
        assert try_parse_part("part1_x.mp4").index == 1


class TestGaps:
    def test_reports_the_hole(self):
        assert missing_parts([1, 2, 4, 5]) == [3]

    def test_multiple_holes_lowest_first(self):
        assert missing_parts([1, 4, 6]) == [2, 3, 5]

    def test_contiguous_run_has_no_gaps(self):
        assert missing_parts([1, 2, 3]) == []

    def test_empty_input_is_not_a_gap(self):
        assert missing_parts([]) == []

    def test_a_run_starting_late_is_missing_its_start(self):
        assert missing_parts([3, 4]) == [1, 2]

    def test_duplicates_are_reported_separately(self):
        assert duplicate_parts([1, 2, 2, 3, 3]) == [2, 3]
        assert duplicate_parts([1, 2, 3]) == []
