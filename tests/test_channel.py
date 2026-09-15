"""
Tests for channel.py, the recording side.

Run with:  python3 -m unittest discover tests
"""

import contextlib
import datetime as dt
import glob
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import channel


def at(state, when):
    """Pin a snapshot's timestamp, so a test can span days without waiting."""
    object.__setattr__(state, "timestamp", when)


def read(root, day, slug):
    path = os.path.join(root, day.strftime("%Y/%m/%d"),
                        day.strftime("%Y%m%d") + f"_{slug}.dat")
    if not os.path.isfile(path):
        return []
    with open(path) as file:
        return [line.split() for line in file.read().strip().split("\n")
                if not line.startswith("#")]


class RecordingTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self._original = channel.DATA_DIR
        channel.DATA_DIR = self.root
        self.addCleanup(setattr, channel, "DATA_DIR", self._original)
        # channel.py announces each new file on stdout; keep it out of the report
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def make(self, **kwargs):
        kwargs.setdefault("thresholds", {"vmon": 5.0})
        kwargs.setdefault("precisions", {"vmon": 2})
        kwargs.setdefault("units", {"vmon": "V"})
        return channel.ChannelState("probe", ["vmon"], **kwargs)

    def feed(self, state, samples):
        """[(datetime, value), ...] through set_state + save_state."""
        for when, value in samples:
            state.set_state({"vmon": value})
            at(state.current, when)
            state.save_state()


class TestSavePrevious(RecordingTestCase):
    """
    The reading before a threshold crossing is worth keeping: a value that sat
    still for days and then jumped otherwise leaves a days-old row as its only
    context for the jump.
    """

    BASE = dt.datetime(2026, 9, 1, 12, 0, 0)

    def stable_then_jump(self, **kwargs):
        state = self.make(**kwargs)
        samples = [(self.BASE + dt.timedelta(minutes=i), v) for i, v in
                   enumerate([100.0, 100.1, 99.9, 100.2, 137.0])]
        self.feed(state, samples)
        return read(self.root, self.BASE.date(), "probe")

    def test_the_reading_before_the_jump_is_recorded(self):
        rows = self.stable_then_jump()
        values = [row[1] for row in rows]
        self.assertIn("100.20", values, "the reading before the jump is missing")
        self.assertIn("137.00", values)
        # and they are adjacent, in order
        self.assertEqual(values[-2:], ["100.20", "137.00"])

    def test_disabled_records_only_the_crossing(self):
        rows = self.stable_then_jump(save_previous=False)
        values = [row[1] for row in rows]
        self.assertNotIn("100.20", values)
        self.assertIn("137.00", values)

    def test_default_is_enabled(self):
        self.assertTrue(self.make().save_previous)

    def test_call_argument_overrides_the_channel_setting(self):
        state = self.make(save_previous=False)
        self.feed(state, [(self.BASE, 100.0), (self.BASE + dt.timedelta(minutes=1), 100.2)])
        state.set_state({"vmon": 137.0})
        at(state.current, self.BASE + dt.timedelta(minutes=2))
        state.save_state(save_previous=True)
        self.assertIn("100.20", [row[1] for row in read(self.root, self.BASE.date(), "probe")])

    def test_previous_is_not_written_twice(self):
        # consecutive crossings: each previous is the row already written last time
        state = self.make()
        self.feed(state, [(self.BASE + dt.timedelta(minutes=i), v)
                          for i, v in enumerate([100.0, 110.0, 120.0, 130.0])])
        rows = read(self.root, self.BASE.date(), "probe")
        stamps = [row[0] for row in rows]
        self.assertEqual(len(stamps), len(set(stamps)), f"duplicate rows: {rows}")

    def test_empty_previous_is_not_written(self):
        # the very first crossing has no preceding reading
        state = self.make()
        state.set_state({"vmon": 100.0})
        at(state.current, self.BASE)
        state.save_state()
        self.assertEqual(len(read(self.root, self.BASE.date(), "probe")), 1)


class TestDayBoundary(RecordingTestCase):
    """A row must be filed under its own date, or a query for that day misses it."""

    def test_previous_reading_goes_in_its_own_day_file(self):
        state = self.make()
        self.feed(state, [
            (dt.datetime(2026, 9, 1, 12, 0, 0), 100.0),
            (dt.datetime(2026, 9, 1, 23, 59, 58), 100.2),   # last reading of the 1st
            (dt.datetime(2026, 9, 2, 0, 0, 1), 137.0),      # crossing, just after midnight
        ])
        first = read(self.root, dt.date(2026, 9, 1), "probe")
        second = read(self.root, dt.date(2026, 9, 2), "probe")

        self.assertIn("2026-09-01T23:59:58", [row[0] for row in first])
        self.assertEqual([row[0] for row in second], ["2026-09-02T00:00:01"])
        for row in second:
            self.assertTrue(row[0].startswith("2026-09-02"),
                            f"row dated {row[0]} filed under 2026-09-02")

    def test_every_row_lands_in_the_file_named_for_its_date(self):
        state = self.make()
        self.feed(state, [
            (dt.datetime(2026, 9, 1, 23, 59, 59), 100.0),
            (dt.datetime(2026, 9, 2, 0, 0, 0), 100.2),
            (dt.datetime(2026, 9, 2, 0, 0, 1), 137.0),
        ])
        for path in glob.glob(os.path.join(self.root, "**/*.dat"), recursive=True):
            stem = os.path.basename(path).split("_")[0]     # YYYYMMDD
            with open(path) as file:
                for line in file:
                    if line.startswith("#"):
                        continue
                    self.assertEqual(line.split()[0][:10].replace("-", ""), stem,
                                     f"{line.strip()!r} is in {os.path.basename(path)}")


class TestThresholds(RecordingTestCase):
    def test_nothing_is_written_below_the_threshold(self):
        state = self.make()
        base = dt.datetime(2026, 9, 1, 12, 0, 0)
        self.feed(state, [(base, 100.0)])
        before = len(read(self.root, base.date(), "probe"))
        self.feed(state, [(base + dt.timedelta(minutes=i), 100.0 + i * 0.1)
                          for i in range(1, 10)])
        self.assertEqual(len(read(self.root, base.date(), "probe")), before)

    def test_force_writes_regardless(self):
        state = self.make()
        base = dt.datetime(2026, 9, 1, 12, 0, 0)
        for i in range(3):
            state.set_state({"vmon": 100.0})
            at(state.current, base + dt.timedelta(minutes=i))
            state.save_state(force=True, save_previous=False)
        self.assertEqual(len(read(self.root, base.date(), "probe")), 3)


if __name__ == "__main__":
    unittest.main()
