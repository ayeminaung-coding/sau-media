"""Slot due-times and backlog ordering. Both are pure; neither needs a database."""

from datetime import UTC, date, datetime

from sau.models import ScheduleSlot
from sau.schedule import BacklogGroup, due_slots, is_due, order_groups, upcoming

BANGKOK = "Asia/Bangkok"  # UTC+7, no DST


def slot(hour, minute=0, *, tz=BANGKOK, enabled=True, fired=None, label="") -> ScheduleSlot:
    return ScheduleSlot(
        label=label, hour=hour, minute=minute, timezone=tz, enabled=enabled, last_fired_on=fired
    )


def utc(y, m, d, hh, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=UTC)


class TestIsDue:
    def test_fires_at_its_local_time(self):
        # 12:00 Bangkok is 05:00 UTC.
        assert is_due(slot(12), utc(2026, 8, 18, 5, 0)) is True

    def test_not_due_before_its_time(self):
        assert is_due(slot(12), utc(2026, 8, 18, 4, 30)) is False

    def test_still_due_inside_the_grace_window(self):
        assert is_due(slot(12), utc(2026, 8, 18, 5, 45)) is True

    def test_skipped_once_the_grace_window_has_passed(self):
        # Better a missed slot than a backlog dumped at an hour nobody chose.
        assert is_due(slot(12), utc(2026, 8, 18, 7, 30)) is False

    def test_at_most_once_per_local_day(self):
        already = slot(12, fired=date(2026, 8, 18))
        assert is_due(already, utc(2026, 8, 18, 5, 5)) is False

    def test_yesterdays_marker_does_not_block_today(self):
        stale = slot(12, fired=date(2026, 8, 17))
        assert is_due(stale, utc(2026, 8, 18, 5, 5)) is True

    def test_a_disabled_slot_never_fires(self):
        assert is_due(slot(12, enabled=False), utc(2026, 8, 18, 5, 0)) is False

    def test_an_unknown_timezone_falls_back_rather_than_raising(self):
        # A mistyped zone should post at a surprising hour, visibly — not take
        # every other slot's release down with it.
        assert is_due(slot(12, tz="Mars/Olympus"), utc(2026, 8, 18, 12, 0)) is True

    def test_grace_window_is_adjustable(self):
        late = utc(2026, 8, 18, 6, 30)  # 90 minutes after a 12:00 Bangkok slot
        assert is_due(slot(12), late, grace_minutes=60) is False
        assert is_due(slot(12), late, grace_minutes=120) is True


class TestDueSlots:
    def test_returns_only_what_is_ready_earliest_first(self):
        slots = [slot(21, label="night"), slot(12, label="lunch"), slot(18, label="evening")]
        # 14:30 Bangkok — lunch is past its grace, evening and night are ahead.
        ready = due_slots(slots, utc(2026, 8, 18, 7, 30))
        assert [s.label for s in ready] == []

        # 18:10 Bangkok: evening only.
        ready = due_slots(slots, utc(2026, 8, 18, 11, 10))
        assert [s.label for s in ready] == ["evening"]

    def test_two_slots_due_at_once_come_back_in_clock_order(self):
        slots = [slot(18, label="evening"), slot(18, 30, label="late")]
        ready = due_slots(slots, utc(2026, 8, 18, 11, 35))  # 18:35 Bangkok
        assert [s.label for s in ready] == ["evening", "late"]


class TestUpcoming:
    def test_returns_the_next_firings_in_order(self):
        slots = [slot(12), slot(18), slot(21)]
        now = utc(2026, 8, 18, 2, 0)  # 09:00 Bangkok — all three still ahead today
        times = upcoming(slots, 5, now)
        assert len(times) == 5
        assert times == sorted(times)
        assert all(t > now for t in times)

    def test_rolls_into_the_next_day(self):
        slots = [slot(12), slot(18), slot(21)]
        now = utc(2026, 8, 18, 15, 0)  # 22:00 Bangkok — today is spent
        times = upcoming(slots, 3, now)
        assert [t.astimezone(UTC).date() for t in times] == [date(2026, 8, 19)] * 3

    def test_disabled_slots_do_not_appear(self):
        slots = [slot(12), slot(18, enabled=False)]
        times = upcoming(slots, 4, utc(2026, 8, 18, 2, 0))
        assert len(times) == 4
        # One firing a day, so four of them span four days.
        assert len({t.astimezone(UTC).date() for t in times}) == 4

    def test_no_slots_means_no_plan(self):
        assert upcoming([], 5, utc(2026, 8, 18, 2, 0)) == []
        assert upcoming([slot(12)], 0, utc(2026, 8, 18, 2, 0)) == []


class TestOrderGroups:
    """The ordering rule a batch-uploaded series depends on."""

    def group(self, asset, seconds, series=None, part=None) -> BacklogGroup:
        return BacklogGroup(
            asset_id=asset,
            created_at=utc(2026, 8, 18, 0, 0).replace(second=seconds),
            series_id=series,
            part_index=part,
        )

    def test_standalone_assets_stay_oldest_first(self):
        groups = [self.group("b", 20), self.group("a", 10)]
        assert [g.asset_id for g in order_groups(groups)] == ["a", "b"]

    def test_a_series_publishes_in_episode_order_not_upload_order(self):
        # The bug this exists to prevent: eight parts uploaded in one batch are
        # timestamped milliseconds apart, in whatever order the uploads
        # finished, and part 5 must not overtake part 3.
        groups = [
            self.group("p3", 10, series="s", part=3),
            self.group("p1", 11, series="s", part=1),
            self.group("p2", 12, series="s", part=2),
        ]
        assert [g.part_index for g in order_groups(groups)] == [1, 2, 3]

    def test_a_series_stays_contiguous(self):
        groups = [
            self.group("p1", 10, series="s", part=1),
            self.group("solo", 20),
            self.group("p2", 30, series="s", part=2),
        ]
        # The series is placed by its earliest part, so a part queued later
        # does not fall behind an unrelated asset.
        assert [g.asset_id for g in order_groups(groups)] == ["p1", "p2", "solo"]

    def test_two_series_are_ordered_by_their_earliest_part(self):
        groups = [
            self.group("b1", 30, series="b", part=1),
            self.group("a1", 10, series="a", part=1),
            self.group("a2", 40, series="a", part=2),
        ]
        assert [g.asset_id for g in order_groups(groups)] == ["a1", "a2", "b1"]

    def test_empty_backlog_orders_to_nothing(self):
        assert order_groups([]) == []
