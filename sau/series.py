"""Reading a part number out of a filename.

A series arrives as a folder of files named `part1_<something>.mp4`, so the
episode order is already in the name and does not need to be retyped. Parsing
it is kept here, pure and separate from the database, because it is the one
piece of this feature that is worth testing exhaustively: get it wrong and
episodes publish out of order, which is the single failure a series cannot
absorb.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

#: `part1_name`, `Part 02 - name`, `ep3_name`, `episode_4_name`.
#:
#: The separator after the digits is required. Without it `part12_x` and
#: `part1_2x` are the same string to a lazy matcher, and a series that
#: silently renumbers itself is worse than one that refuses to parse.
_PART_RE = re.compile(
    r"^\s*(?:part|ep|episode)[\s_\-.]*(\d{1,4})(?:[\s_\-.]+(?P<label>.*))?$",
    re.IGNORECASE,
)


class SeriesNameError(ValueError):
    """A filename does not carry a part number."""


@dataclass(frozen=True)
class ParsedPart:
    """What a series filename decomposes into."""

    index: int
    #: Whatever followed the part number, punctuation tidied. Free text: it is
    #: shown to the operator to confirm the right file matched, never published.
    label: str
    filename: str


def parse_part(filename: str) -> ParsedPart:
    """Pull the episode number out of a series filename.

    Raises `SeriesNameError` rather than guessing. A file that does not follow
    the convention is an operator mistake worth surfacing at upload time, not
    an asset to quietly assign a position to.
    """
    stem = PurePosixPath(filename).stem
    match = _PART_RE.match(stem)
    if match is None:
        raise SeriesNameError(
            f"{filename!r} does not start with a part number. "
            "Expected something like 'part1_name.mp4'."
        )

    index = int(match.group(1))
    if index < 1:
        # part0 is almost always a numbering slip, and it would sort ahead of
        # the real first episode.
        raise SeriesNameError(f"{filename!r} has part number {index}; parts start at 1.")

    label = (match.group("label") or "").strip()
    return ParsedPart(index=index, label=re.sub(r"[_\-.]+", " ", label).strip(), filename=filename)


def try_parse_part(filename: str) -> ParsedPart | None:
    """`parse_part`, but None instead of an exception. For bulk sorting."""
    try:
        return parse_part(filename)
    except SeriesNameError:
        return None


def missing_parts(indices: Iterable[int]) -> list[int]:
    """Episode numbers absent from an otherwise contiguous run, lowest first.

    A gap means a file was not uploaded, and the operator wants to know before
    the release schedule is built around what is there.
    """
    present = {i for i in indices if i >= 1}
    if not present:
        return []
    return [n for n in range(1, max(present)) if n not in present]


def duplicate_parts(indices: Iterable[int]) -> list[int]:
    """Episode numbers claimed more than once, lowest first."""
    seen: set[int] = set()
    repeats: set[int] = set()
    for index in indices:
        if index in seen:
            repeats.add(index)
        seen.add(index)
    return sorted(repeats)
