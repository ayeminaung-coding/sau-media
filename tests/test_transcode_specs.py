"""Rendition specs and the ffmpeg filter string."""

from sau.models import Platform
from sau.transcode import SPECS, _scale_filter


def test_every_platform_has_a_spec():
    assert set(SPECS) == set(Platform)


def test_vertical_targets_are_nine_by_sixteen():
    for platform in (Platform.TIKTOK, Platform.FACEBOOK_REEL):
        spec = SPECS[platform]
        assert spec.width * 16 == spec.height * 9


def test_reels_are_trimmed_to_the_platform_limit():
    assert SPECS[Platform.FACEBOOK_REEL].max_duration_seconds == 90


def test_padded_specs_letterbox_to_exact_dimensions():
    chain = _scale_filter(SPECS[Platform.TIKTOK])
    assert "force_original_aspect_ratio=decrease" in chain
    assert "pad=1080:1920" in chain


def test_unpadded_specs_keep_aspect_and_force_even_dimensions():
    chain = _scale_filter(SPECS[Platform.FACEBOOK_VIDEO])
    assert "pad=" not in chain
    # libx264 rejects odd dimensions after a decrease-fit scale.
    assert "trunc(iw/2)*2" in chain
