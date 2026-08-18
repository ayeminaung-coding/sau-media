"""Rendering an episode's caption from the series' stored copy.

For a serialised show the caption is overwhelmingly structural -- series
title, episode number, a pointer to the next part, a fixed hashtag block --
and exactly one line differs between episodes. So the shape is a stored
template plus a per-part `hook`, not a generated paragraph.

Everything here is pure: strings in, strings out, no database and no network.
That is deliberate. This is the path that runs when a part is actually
published, and it has to work with the caption generator switched off,
misconfigured, or rate-limited.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from sau.models import CAPTION_LIMITS, TITLE_LIMITS, Platform, Series

#: Placeholders are `{name}`. An unknown name is left in the output verbatim
#: rather than raising or blanking, so an operator's typo shows up in the
#: preview as itself instead of as a silent hole.
_FIELD_RE = re.compile(r"\{(\w+)\}")

#: The starting point a new series is created with, and nothing more -- every
#: one of these is a stored column the operator overwrites in the console. They
#: are only defaults so that a series created in ten seconds still publishes
#: something coherent.
DEFAULT_CAPTION_TEMPLATE = "အပိုင်း ({part}) {series}\n\n{hook}\n\n{hashtags}"
DEFAULT_TITLE_TEMPLATE = "အပိုင်း ({part}) {series}"
#: Empty by default. A separate teaser line is redundant when the hook itself
#: ends on the cliffhanger, which is how the style this was built for reads.
DEFAULT_NEXT_TEASER_TEMPLATE = ""


@dataclass(frozen=True)
class Rendered:
    """What one part publishes as, on one platform."""

    caption: str
    title: str


@dataclass(frozen=True)
class SeriesCopy:
    """The caption material of a series, detached from the ORM row.

    Detached so the render path can be exercised without a database, which is
    what keeps these rules in the test suite rather than in production.
    """

    title_local: str = ""
    title_en: str = ""
    synopsis: str = ""
    language: str = "Burmese"
    style_example: str = ""
    caption_template: str = DEFAULT_CAPTION_TEMPLATE
    title_template: str = DEFAULT_TITLE_TEMPLATE
    next_teaser_template: str = DEFAULT_NEXT_TEASER_TEMPLATE
    hashtags: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_series(cls, series: Series) -> SeriesCopy:
        return cls(
            title_local=series.title_local,
            title_en=series.title_en,
            synopsis=series.synopsis,
            language=series.language,
            style_example=series.style_example,
            caption_template=series.caption_template or DEFAULT_CAPTION_TEMPLATE,
            title_template=series.title_template or DEFAULT_TITLE_TEMPLATE,
            next_teaser_template=series.next_teaser_template or DEFAULT_NEXT_TEASER_TEMPLATE,
            hashtags=dict(series.hashtags or {}),
        )

    def hashtags_for(self, platform: Platform) -> str:
        return self.hashtags.get(platform.value, "")


def substitute(template: str, values: Mapping[str, str]) -> str:
    """Replace every known `{name}`, leaving unknown ones untouched."""
    return _FIELD_RE.sub(
        lambda match: values.get(match.group(1), match.group(0)),
        template,
    )


def tidy(text: str) -> str:
    """Close the holes an empty placeholder leaves behind.

    A blank `{hook}` or a final episode's blank `{next_teaser}` would otherwise
    leave a stranded empty line, or two, in the middle of the caption. Runs of
    blank lines collapse to one and trailing spaces go, so the same template
    reads correctly whether or not every field was filled.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    return "\n".join(out).strip()


def fit(text: str, limit: int) -> str:
    """Trim `text` to `limit` characters, preferring a clean break.

    Backs up to the last whitespace so a hashtag or word is not severed
    mid-token -- but only if that costs less than a fifth of the budget.
    Chinese runs without spaces for whole sentences, so an unguarded backoff
    could discard most of a line looking for a space that is not there.
    """
    if limit <= 0 or len(text) <= limit:
        return text

    budget = limit - 1  # the ellipsis has to fit inside the platform's limit
    cut = text[:budget]
    space = cut.rfind(" ")
    if space > budget * 0.8:
        cut = cut[:space]
    return cut.rstrip() + "…"


def context(
    copy: SeriesCopy,
    *,
    part_index: int,
    total: int,
    hook: str,
    platform: Platform,
) -> dict[str, str]:
    """Every placeholder a template may use, resolved for one part."""
    has_next = part_index < total
    base = {
        "series": copy.title_local,
        "series_en": copy.title_en,
        "synopsis": copy.synopsis,
        "part": str(part_index),
        "total": str(total),
        "next_part": str(part_index + 1) if has_next else "",
        "hook": hook.strip(),
        "hashtags": copy.hashtags_for(platform),
    }
    # The teaser is itself a template, and it renders empty on the last part:
    # the final episode must not promise a next one that never arrives.
    base["next_teaser"] = substitute(copy.next_teaser_template, base) if has_next else ""
    return base


def render(
    copy: SeriesCopy,
    *,
    part_index: int,
    total: int,
    hook: str,
    platform: Platform,
) -> Rendered:
    """Render one part's caption and title for one platform, within its limits."""
    values = context(copy, part_index=part_index, total=total, hook=hook, platform=platform)

    caption = fit(tidy(substitute(copy.caption_template, values)), CAPTION_LIMITS[platform])

    # A zero title limit means the platform has no title field at all; sending
    # one is not an error, it is just silently dropped, so do not build it.
    title_limit = TITLE_LIMITS[platform]
    title = fit(tidy(substitute(copy.title_template, values)), title_limit) if title_limit else ""

    return Rendered(caption=caption, title=title)
