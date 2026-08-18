"""Prompt shape, and reading back a model reply that may be badly wrapped."""

import pytest

from sau.captions.generate import PartBrief, build_prompt, parse_hooks
from sau.captions.providers import CaptionError
from sau.captions.template import SeriesCopy

COPY = SeriesCopy(title_zh="仙路", title_en="Immortal Road", synopsis="A boy finds a sword.")
BRIEFS = [PartBrief(index=1, label="part1_open"), PartBrief(index=2), PartBrief(index=3)]


class TestBuildPrompt:
    def test_names_every_episode(self):
        prompt = build_prompt(COPY, BRIEFS)
        for index in (1, 2, 3):
            assert f"part {index}" in prompt

    def test_carries_the_synopsis(self):
        assert "A boy finds a sword." in build_prompt(COPY, BRIEFS)

    def test_states_the_length_limit(self):
        assert "40 characters" in build_prompt(COPY, BRIEFS, max_chars=40)

    def test_states_the_language(self):
        assert "Thai" in build_prompt(COPY, BRIEFS, language="Thai")

    def test_settled_hooks_are_marked_as_fixed(self):
        # This is what makes a re-run extend the arc rather than rewrite lines
        # the operator already approved.
        briefs = [PartBrief(index=1, hook="已经写好了"), PartBrief(index=2)]
        prompt = build_prompt(COPY, briefs)
        assert "ALREADY WRITTEN" in prompt
        assert "已经写好了" in prompt

    def test_asks_for_one_call_covering_the_whole_arc(self):
        prompt = build_prompt(COPY, BRIEFS)
        assert "arc" in prompt
        assert "JSON" in prompt


class TestParseHooks:
    def test_reads_the_documented_shape(self):
        reply = '{"hooks": [{"part": 1, "hook": "a"}, {"part": 2, "hook": "b"}]}'
        assert parse_hooks(reply, [1, 2]) == {1: "a", 2: "b"}

    def test_tolerates_a_code_fence(self):
        reply = '```json\n{"hooks": [{"part": 1, "hook": "a"}]}\n```'
        assert parse_hooks(reply, [1]) == {1: "a"}

    def test_tolerates_a_bare_list(self):
        assert parse_hooks('[{"part": 1, "hook": "a"}]', [1]) == {1: "a"}

    def test_accepts_a_part_number_sent_as_a_string(self):
        assert parse_hooks('{"hooks": [{"part": "2", "hook": "b"}]}', [2]) == {2: "b"}

    def test_drops_hooks_for_episodes_that_do_not_exist(self):
        reply = '{"hooks": [{"part": 1, "hook": "a"}, {"part": 99, "hook": "ghost"}]}'
        assert parse_hooks(reply, [1]) == {1: "a"}

    def test_drops_blank_and_non_string_hooks(self):
        reply = (
            '{"hooks": [{"part": 1, "hook": "  "}, '
            '{"part": 2, "hook": 5}, {"part": 3, "hook": "c"}]}'
        )
        assert parse_hooks(reply, [1, 2, 3]) == {3: "c"}

    def test_non_json_is_an_error_not_a_silent_empty(self):
        with pytest.raises(CaptionError):
            parse_hooks("I'd be happy to help!", [1])

    def test_valid_json_without_hooks_is_an_error(self):
        with pytest.raises(CaptionError):
            parse_hooks('{"result": "ok"}', [1])

    def test_nothing_usable_is_an_error(self):
        with pytest.raises(CaptionError):
            parse_hooks('{"hooks": [{"part": 99, "hook": "x"}]}', [1])
