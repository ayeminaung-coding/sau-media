"""Caption drafting and rendering for serialised uploads.

Two halves, kept apart on purpose:

- `template` renders the published text from stored copy. Pure, offline, and
  on the publish path -- it must work with every generator switched off.
- `generate` and `providers` draft the one line per episode that actually
  varies. Upstream of publishing, operator-triggered, and allowed to fail.
"""

from sau.captions.generate import PartBrief, generate_hooks
from sau.captions.providers import CaptionError, available, complete
from sau.captions.template import (
    DEFAULT_CAPTION_TEMPLATE,
    DEFAULT_NEXT_TEASER_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    Rendered,
    SeriesCopy,
    render,
)

__all__ = [
    "DEFAULT_CAPTION_TEMPLATE",
    "DEFAULT_NEXT_TEASER_TEMPLATE",
    "DEFAULT_TITLE_TEMPLATE",
    "CaptionError",
    "PartBrief",
    "Rendered",
    "SeriesCopy",
    "available",
    "complete",
    "generate_hooks",
    "render",
]
