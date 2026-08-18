"""Graph returns relative permalinks; jobs must store absolute URLs."""

from sau.platforms.facebook.publisher import _permalink


def test_relative_permalink_is_made_absolute():
    assert _permalink({"permalink_url": "/reel/123"}) == "https://www.facebook.com/reel/123"


def test_absolute_permalink_is_left_alone():
    url = "https://www.facebook.com/watch/?v=9"
    assert _permalink({"permalink_url": url}) == url


def test_missing_permalink_is_none():
    assert _permalink({}) is None
