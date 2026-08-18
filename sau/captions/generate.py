"""Drafting the per-episode hook line, for a whole series in one call.

The unit of generation is the *series*, not the video, and that is the only
interesting decision here. Asked for one caption at a time, a model cannot
write a cliffhanger: it has no idea what part 4 is going to open with, so
every hook comes out as an interchangeable logline. Asked for all of them at
once, against the synopsis, it can build a ladder -- part 3 ends on the
question part 4 answers.

It is also cheaper by roughly the number of episodes, which is the smaller
reason but not a bad one.

What comes back is always a draft. It lands in `SeriesPart.hook`, the operator
edits it, and `captions.template` renders the published text from it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sau.captions.providers import CaptionError, complete
from sau.captions.template import SeriesCopy
from sau.config import Settings
from sau.logging import get_logger

log = get_logger(__name__)

#: A hook is the one paragraph under the title line. Sized from real captions
#: rather than from the platform limits, which are far larger than anything
#: worth reading: two sentences of Burmese lands around 200 characters.
DEFAULT_HOOK_MAX_CHARS = 240

#: Models like to wrap JSON in a fence even when asked for raw JSON, and
#: OpenRouter's `response_format` is advisory on some upstream providers.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PartBrief:
    """What the generator is told about one episode."""

    index: int
    #: The descriptive tail of the filename, if the operator put one there.
    label: str = ""
    duration_seconds: float | None = None
    #: An existing hook. Present ones are shown to the model as already
    #: settled, so a regeneration extends the arc instead of contradicting it.
    hook: str = ""


def build_prompt(
    copy: SeriesCopy,
    briefs: Sequence[PartBrief],
    *,
    language: str | None = None,
    max_chars: int = DEFAULT_HOOK_MAX_CHARS,
) -> str:
    """Compose the single request that drafts every missing hook."""
    total = len(briefs)
    language = language or copy.language
    lines = [
        f"- part {b.index}"
        + (f' — file label: "{b.label}"' if b.label else "")
        + (f" — {b.duration_seconds:.0f}s" if b.duration_seconds else "")
        + (f'\n  ALREADY WRITTEN, do not change: "{b.hook}"' if b.hook.strip() else "")
        for b in briefs
    ]

    # An example of the wanted voice beats any amount of description of it, and
    # the gap widens the less of a language the model has seen. For Burmese
    # this is the difference between usable output and a stilted translation.
    style = (
        [
            "HOUSE STYLE — one real caption from this account. Match its voice,",
            "sentence rhythm, punctuation and emoji use as closely as you can:",
            "",
            copy.style_example.strip(),
            "",
        ]
        if copy.style_example.strip()
        else []
    )

    return "\n".join(
        [
            f"You write social-media hooks in {language} for a serialised animation.",
            "",
            f"Series title: {copy.title_local or copy.title_en or '(untitled)'}",
            f"Also known as: {copy.title_en}" if copy.title_en and copy.title_local else "",
            f"Episodes: {total}",
            "",
            "Synopsis:",
            copy.synopsis or "(none given — infer a plausible arc from the titles)",
            "",
            *style,
            "Episodes to write for:",
            *lines,
            "",
            "Write ONE hook per episode, for the ones not already written.",
            "A hook is the paragraph that sits under the title line of the caption.",
            "Rules:",
            f"- Write in {language}. Natural, colloquial {language} — not a translation.",
            f"- Around {max_chars} characters; that is a hard ceiling, not a target.",
            "- A hook is a reason to watch THIS episode, not a summary of it.",
            "- Do not spoil how the episode ends.",
            "- Land on the question the next episode answers, so the series reads as",
            "  one arc. The final episode closes it instead of opening another.",
            "- Emoji: match the house style — the same kind, and the same number.",
            "  If there is no house style, one or two at the end, or none.",
            "- No hashtags and no 'part N' prefix. The template adds both.",
            "",
            'Reply with JSON only: {"hooks": [{"part": 1, "hook": "..."}]}',
        ]
    )


def parse_hooks(reply: str, valid: Iterable[int]) -> dict[int, str]:
    """Read `{part: hook}` out of a model reply, discarding anything unusable.

    Deliberately forgiving about the envelope and strict about the contents: a
    hook for an episode that does not exist, or a non-string hook, is dropped
    rather than allowed to overwrite a real part.
    """
    allowed = set(valid)
    text = _FENCE_RE.sub("", reply.strip())

    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaptionError(f"caption provider did not return JSON: {text[:200]}") from exc

    rows = payload.get("hooks") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise CaptionError("caption reply had no 'hooks' list")

    hooks: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("part"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        hook = row.get("hook")
        if index in allowed and isinstance(hook, str) and hook.strip():
            hooks[index] = hook.strip()

    if not hooks:
        raise CaptionError("caption reply contained no usable hooks")
    return hooks


def generate_hooks(
    copy: SeriesCopy,
    briefs: Sequence[PartBrief],
    *,
    language: str | None = None,
    max_chars: int = DEFAULT_HOOK_MAX_CHARS,
    settings: Settings | None = None,
) -> tuple[dict[int, str], str]:
    """Draft a hook for every part, returning them and the provider that served."""
    if not briefs:
        return {}, ""

    prompt = build_prompt(copy, briefs, language=language, max_chars=max_chars)
    reply, provider = complete(prompt, settings)
    hooks = parse_hooks(reply, (b.index for b in briefs))

    # Trim rather than reject: a model that overshoots the limit by a few
    # characters has still done the useful part of the work, and the operator
    # is going to read every line before any of it publishes.
    trimmed = {index: hook[:max_chars].strip() for index, hook in hooks.items()}
    log.info("captions.generated", provider=provider, parts=len(trimmed))
    return trimmed, provider
