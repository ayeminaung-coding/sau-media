"""The render path runs at publish time with every generator switched off."""

from sau.captions.template import (
    Rendered,
    SeriesCopy,
    fit,
    render,
    substitute,
    tidy,
)
from sau.models import CAPTION_LIMITS, TITLE_LIMITS, Platform

COPY = SeriesCopy(
    title_zh="仙路",
    title_en="Immortal Road",
    caption_template=(
        "《{series_zh}》第{part}集 / 共{total}集\n\n{hook}\n\n{next_teaser}\n{hashtags}"
    ),
    title_template="《{series_zh}》第{part}集",
    next_teaser_template="下集预告：第{next_part}集",
    hashtags={"tiktok": "#AI动画 #国漫", "facebook_reel": "#AIAnimation"},
)


class TestSubstitute:
    def test_replaces_known_fields(self):
        assert substitute("a{x}b", {"x": "1"}) == "a1b"

    def test_leaves_unknown_fields_visible(self):
        # An operator's typo should show up in the preview as itself, not as a
        # silent hole they have to notice the absence of.
        assert substitute("a{nope}b", {"x": "1"}) == "a{nope}b"

    def test_empty_value_substitutes_to_nothing(self):
        assert substitute("a{x}b", {"x": ""}) == "ab"


class TestTidy:
    def test_collapses_the_hole_an_empty_field_leaves(self):
        assert tidy("one\n\n\n\ntwo") == "one\n\ntwo"

    def test_strips_leading_and_trailing_blank_lines(self):
        assert tidy("\n\nbody\n\n") == "body"

    def test_drops_trailing_spaces(self):
        assert tidy("a   \nb") == "a\nb"


class TestFit:
    def test_short_text_is_untouched(self):
        assert fit("abc", 10) == "abc"

    def test_truncation_fits_inside_the_limit(self):
        assert len(fit("x" * 100, 20)) <= 20

    def test_prefers_a_word_boundary(self):
        assert fit("hello there wonderful world", 20).startswith("hello there")
        assert "…" in fit("hello there wonderful world", 20)

    def test_chinese_without_spaces_is_not_gutted(self):
        # Backing up to the last space would discard almost everything, since
        # there is no space to find. The guard is what keeps this usable.
        text = "这是一段没有空格的中文文字" * 5
        assert len(fit(text, 20)) >= 15

    def test_zero_limit_means_no_field(self):
        assert fit("anything", 0) == "anything"


class TestRender:
    def test_renders_a_middle_episode(self):
        out = render(COPY, part_index=3, total=8, hook="他终于开口了", platform=Platform.TIKTOK)
        assert isinstance(out, Rendered)
        assert "第3集" in out.caption
        assert "共8集" in out.caption
        assert "他终于开口了" in out.caption
        assert "下集预告：第4集" in out.caption
        assert "#AI动画" in out.caption

    def test_final_episode_promises_no_next_one(self):
        out = render(COPY, part_index=8, total=8, hook="结局", platform=Platform.TIKTOK)
        assert "下集预告" not in out.caption
        # And the line it occupied does not survive as a blank one.
        assert "\n\n\n" not in out.caption

    def test_empty_hook_leaves_no_hole(self):
        out = render(COPY, part_index=2, total=8, hook="", platform=Platform.TIKTOK)
        assert "\n\n\n" not in out.caption
        assert out.caption.startswith("《仙路》第2集")

    def test_hashtags_are_per_platform(self):
        tiktok = render(COPY, part_index=1, total=3, hook="h", platform=Platform.TIKTOK)
        reel = render(COPY, part_index=1, total=3, hook="h", platform=Platform.FACEBOOK_REEL)
        assert "#AI动画" in tiktok.caption
        assert "#AIAnimation" in reel.caption
        assert "#AI动画" not in reel.caption

    def test_platform_with_no_hashtags_configured_renders_without_them(self):
        # Last part, so neither a hashtag block nor a teaser follows the hook —
        # and neither leaves a trailing blank line behind.
        out = render(COPY, part_index=3, total=3, hook="h", platform=Platform.FACEBOOK_VIDEO)
        assert "#" not in out.caption
        assert out.caption.endswith("h")

    def test_reels_get_no_title_because_they_have_no_field(self):
        out = render(COPY, part_index=1, total=3, hook="h", platform=Platform.FACEBOOK_REEL)
        assert out.title == ""
        assert TITLE_LIMITS[Platform.FACEBOOK_REEL] == 0

    def test_title_is_built_where_the_platform_has_one(self):
        out = render(COPY, part_index=1, total=3, hook="h", platform=Platform.TIKTOK)
        assert out.title == "《仙路》第1集"

    def test_output_never_exceeds_the_platform_limit(self):
        long_copy = SeriesCopy(
            title_zh="仙路",
            caption_template="{hook}",
            title_template="{hook}",
            next_teaser_template="",
        )
        for platform in Platform:
            out = render(
                long_copy, part_index=1, total=1, hook="x" * 9000, platform=platform
            )
            assert len(out.caption) <= CAPTION_LIMITS[platform]
            assert len(out.title) <= TITLE_LIMITS[platform]

    def test_defaults_render_without_any_configuration(self):
        out = render(SeriesCopy(), part_index=1, total=2, hook="", platform=Platform.TIKTOK)
        assert out.caption  # a series created in ten seconds still publishes something
