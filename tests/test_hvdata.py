"""
Tests for hvdata, the reader for recorded channel values.

Run with:  python3 -m unittest discover tests

The recorded tree is gitignored, so every fixture here is synthesized in a
temporary directory. One test reads the repository's own data/ directory if it
happens to be populated, and skips otherwise.
"""

import datetime as dt
import os
import sys
import tempfile
import unittest
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hvdata


def write_file(root, day, slug, header, rows, index=0):
    """Create one recorded file. `day` is a date, `rows` a list of text lines."""
    directory = os.path.join(root, day.strftime("%Y/%m/%d"))
    os.makedirs(directory, exist_ok=True)
    suffix = f"_{index}" if index else ""
    path = os.path.join(directory, f"{day.strftime('%Y%m%d')}_{slug}{suffix}.dat")
    with open(path, "w") as file:
        file.write(header + "\n")
        for row in rows:
            file.write(row + "\n")
    return path


DAY = dt.date(2026, 9, 11)
NEXT_DAY = dt.date(2026, 9, 12)


class TestParseHeader(unittest.TestCase):
    def test_commented_and_bare_headers_are_equivalent(self):
        for line in ("# Time vmon[V] imon[uA]", "Time vmon[V] imon[uA]"):
            columns, units = hvdata.parse_header(line)
            self.assertEqual(columns, ["vmon", "imon"])
            self.assertEqual(units, {"vmon": "V", "imon": "uA"})

    def test_column_without_unit(self):
        columns, units = hvdata.parse_header("# Time state")
        self.assertEqual(columns, ["state"])
        self.assertEqual(units, {"state": ""})

    def test_empty_unit_brackets(self):
        _, units = hvdata.parse_header("# Time interlock[]")
        self.assertEqual(units, {"interlock": ""})


class TestUnitFactor(unittest.TestCase):
    def test_si_prefixes(self):
        self.assertEqual(hvdata.unit_factor("kV", "V"), 1e3)
        self.assertAlmostEqual(hvdata.unit_factor("mV", "V"), 1e-3)
        self.assertAlmostEqual(hvdata.unit_factor("uA", "mA"), 1e-3)
        self.assertEqual(hvdata.unit_factor("V", "V"), 1.0)

    def test_single_character_unit_is_not_read_as_a_prefix(self):
        # "m" alone is a unit, not the milli prefix on an empty unit
        self.assertEqual(hvdata.unit_factor("m", "m"), 1.0)

    def test_different_quantities_refuse_to_convert(self):
        with self.assertRaises(ValueError):
            hvdata.unit_factor("V", "A")


class TestTimestampFormats(unittest.TestCase):
    """The writer changed from "%Y-%m-%d %H:%M:%S" to ISO-8601 mid-life."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def read(self, slug="ch"):
        return hvdata.read_channel(slug, DAY, DAY, data_dir=self.root)

    def test_legacy_space_separated_timestamps(self):
        write_file(self.root, DAY, "ch", "Time vmon[V]",
                   ["2026-09-11 10:00:00 1.0", "2026-09-11 10:00:01 2.0"])
        frame = self.read()
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame["vmon"].tolist(), [1.0, 2.0])

    def test_iso_timestamps(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]",
                   ["2026-09-11T10:00:00 1.0", "2026-09-11T10:00:01 2.0"])
        self.assertEqual(len(self.read()), 2)

    def test_both_formats_in_one_file(self):
        # exactly what the file open at the moment of the change looks like
        write_file(self.root, DAY, "ch", "Time vmon[V]",
                   ["2026-09-11 10:00:00 1.0", "2026-09-11T10:00:01 2.0"])
        frame = self.read()
        self.assertEqual(len(frame), 2)
        self.assertTrue(frame.index.is_monotonic_increasing)

    def test_bare_header_is_not_parsed_as_a_row(self):
        # "Time vmon[V]" has as many tokens as a data row of one column
        write_file(self.root, DAY, "ch", "Time vmon[V]", ["2026-09-11 10:00:00 1.0"])
        frame = self.read()
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.index.isna().sum(), 0)


class TestMalformedInput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_truncated_final_line_is_skipped_not_fatal(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V] imon[uA]",
                   ["2026-09-11T10:00:00 1.0 0.1", "2026-09-11T10:00:01 2.0"])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = hvdata.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(len(frame), 1)
        self.assertTrue(any(w.category is hvdata.MalformedLineWarning for w in caught))

    def test_literal_nan_becomes_a_real_nan(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]",
                   ["2026-09-11T10:00:00 nan", "2026-09-11T10:00:01 2.0"])
        frame = hvdata.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(len(frame), 2)
        self.assertTrue(frame["vmon"].isna().iloc[0])


class TestSiblingFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_siblings_sort_numerically_not_lexicographically(self):
        write_file(self.root, DAY, "ch", "# Time v[V]", ["2026-09-11T10:00:00 0"])
        for index in (2, 10):
            write_file(self.root, DAY, "ch", "# Time v[V]",
                       [f"2026-09-11T10:00:0{0} {index}"], index=index)
        found = hvdata.find_files("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual([f.index for f in found], [0, 2, 10])

    def test_prefix_collision_does_not_leak_between_channels(self):
        write_file(self.root, DAY, "gem", "# Time v[V]", ["2026-09-11T10:00:00 1"])
        write_file(self.root, DAY, "gemtop", "# Time v[V]", ["2026-09-11T10:00:00 2"])
        found = hvdata.find_files("gem", DAY, DAY, data_dir=self.root)
        self.assertEqual([f.name for f in found], ["20260911_gem.dat"])

    def test_units_convert_rescales_and_warns(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = hvdata.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(frame["vmon"].tolist(), [100.0, 99500.0])
        self.assertEqual(hvdata.units_of(frame), {"vmon": "V"})
        self.assertTrue(any(w.category is hvdata.UnitMismatchWarning for w in caught))

    def test_units_raise_refuses_to_guess(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        with self.assertRaises(ValueError):
            hvdata.read_channel("ch", DAY, DAY, data_dir=self.root, units="raise")

    def test_units_keep_tags_the_source(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        frame = hvdata.read_channel("ch", DAY, DAY, data_dir=self.root, units="keep")
        self.assertEqual(frame["vmon"].tolist(), [100.0, 99.5])
        self.assertEqual(sorted(set(frame["source_file"])),
                         ["20260911_ch.dat", "20260911_ch_1.dat"])

    def test_incompatible_quantities_raise_even_when_converting(self):
        write_file(self.root, DAY, "ch", "# Time x[V]", ["2026-09-11T10:00:00 1.0"])
        write_file(self.root, DAY, "ch", "# Time x[A]",
                   ["2026-09-11T11:00:00 2.0"], index=1)
        with self.assertRaises(ValueError):
            hvdata.read_channel("ch", DAY, DAY, data_dir=self.root)


class TestChannelResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_file(self.root, DAY, "meshright", "# Time vmon[V]",
                   ["2026-09-11T10:00:00 1.0"])

    def test_display_name_slug_and_casing_all_resolve(self):
        for name in ("mesh right", "meshright", "MeshRight", "MESH RIGHT"):
            frame = hvdata.read_channel(name, DAY, DAY, data_dir=self.root)
            self.assertEqual(len(frame), 1, name)

    def test_unknown_channel_raises_and_lists_what_exists(self):
        with self.assertRaises(FileNotFoundError) as context:
            hvdata.read_channel("nope", DAY, DAY, data_dir=self.root)
        self.assertIn("meshright", str(context.exception))
        self.assertIn(self.root, str(context.exception))

    def test_list_channels(self):
        self.assertEqual(hvdata.list_channels(DAY, DAY, data_dir=self.root), ["meshright"])


class TestDateRange(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_file(self.root, DAY, "ch", "# Time v[V]",
                   ["2026-09-11T08:00:00 1", "2026-09-11T20:00:00 2"])
        write_file(self.root, NEXT_DAY, "ch", "# Time v[V]", ["2026-09-12T08:00:00 3"])

    def test_range_spans_days(self):
        frame = hvdata.read_channel("ch", DAY, NEXT_DAY, data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [1, 2, 3])

    def test_bare_end_date_includes_the_whole_day(self):
        frame = hvdata.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [1, 2])   # 20:00 must be included

    def test_times_narrow_the_range(self):
        frame = hvdata.read_channel("ch", "2026-09-11 09:00", "2026-09-12 09:00",
                                    data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [2, 3])

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            hvdata.read_channel("ch", NEXT_DAY, DAY, data_dir=self.root)


class TestParseWhen(unittest.TestCase):
    def test_iso_forms(self):
        self.assertEqual(hvdata.parse_when("2026-09-11"), dt.datetime(2026, 9, 11))
        self.assertEqual(hvdata.parse_when("2026-09-11 13:05"), dt.datetime(2026, 9, 11, 13, 5))
        self.assertEqual(hvdata.parse_when("2026-09-11T13:05:07"),
                         dt.datetime(2026, 9, 11, 13, 5, 7))

    def test_bare_date_end_of_day(self):
        stamp = hvdata.parse_when("2026-09-11", end_of_day=True)
        self.assertEqual((stamp.hour, stamp.minute, stamp.second), (23, 59, 59))

    def test_a_date_with_a_time_ignores_end_of_day(self):
        self.assertEqual(hvdata.parse_when("2026-09-11 13:05", end_of_day=True),
                         dt.datetime(2026, 9, 11, 13, 5))

    def test_keywords_and_offsets(self):
        self.assertEqual(hvdata.parse_when("today").date(), dt.date.today())
        self.assertEqual(hvdata.parse_when("yesterday").date(),
                         dt.date.today() - dt.timedelta(days=1))
        delta = dt.datetime.now() - hvdata.parse_when("-2h")
        self.assertAlmostEqual(delta.total_seconds(), 7200, delta=5)


class TestToNumpy(unittest.TestCase):
    def test_shapes_and_dtypes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_file(tmp.name, DAY, "ch", "# Time v[V] i[uA]",
                   ["2026-09-11T10:00:00 1.0 0.1", "2026-09-11T10:00:01 2.0 0.2"])
        frame = hvdata.read_channel("ch", DAY, DAY, data_dir=tmp.name)
        seconds, values, names = hvdata.to_numpy(frame)
        self.assertEqual(seconds.shape, (2,))
        self.assertEqual(values.shape, (2, 2))
        self.assertEqual(names, ["v", "i"])
        self.assertEqual(str(seconds.dtype), "float64")


class TestAgainstRepositoryData(unittest.TestCase):
    """Smoke test against whatever is really in data/, if anything."""

    def setUp(self):
        import channel
        if not hvdata.list_channels("2000-01-01", "2100-01-01", data_dir=channel.DATA_DIR):
            self.skipTest("no recorded data in the repository's data/ directory")
        self.root = channel.DATA_DIR

    def test_every_channel_parses(self):
        names = hvdata.list_channels("2000-01-01", "2100-01-01", data_dir=self.root)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name in names:
                frame = hvdata.read_channel(name, "2000-01-01", "2100-01-01",
                                            data_dir=self.root)
                self.assertTrue(frame.index.is_monotonic_increasing, name)
                self.assertEqual(frame.index.isna().sum(), 0, name)


if __name__ == "__main__":
    unittest.main()
