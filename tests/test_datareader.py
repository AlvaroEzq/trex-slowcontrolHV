"""
Tests for datareader, the reader for recorded channel values.

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

import datareader


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
            columns, units = datareader.parse_header(line)
            self.assertEqual(columns, ["vmon", "imon"])
            self.assertEqual(units, {"vmon": "V", "imon": "uA"})

    def test_column_without_unit(self):
        columns, units = datareader.parse_header("# Time state")
        self.assertEqual(columns, ["state"])
        self.assertEqual(units, {"state": ""})

    def test_empty_unit_brackets(self):
        _, units = datareader.parse_header("# Time interlock[]")
        self.assertEqual(units, {"interlock": ""})


class TestUnitFactor(unittest.TestCase):
    def test_si_prefixes(self):
        self.assertEqual(datareader.unit_factor("kV", "V"), 1e3)
        self.assertAlmostEqual(datareader.unit_factor("mV", "V"), 1e-3)
        self.assertAlmostEqual(datareader.unit_factor("uA", "mA"), 1e-3)
        self.assertEqual(datareader.unit_factor("V", "V"), 1.0)

    def test_single_character_unit_is_not_read_as_a_prefix(self):
        # "m" alone is a unit, not the milli prefix on an empty unit
        self.assertEqual(datareader.unit_factor("m", "m"), 1.0)

    def test_different_quantities_refuse_to_convert(self):
        with self.assertRaises(ValueError):
            datareader.unit_factor("V", "A")


class TestTimestampFormats(unittest.TestCase):
    """The writer changed from "%Y-%m-%d %H:%M:%S" to ISO-8601 mid-life."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def read(self, slug="ch"):
        return datareader.read_channel(slug, DAY, DAY, data_dir=self.root)

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
            frame = datareader.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(len(frame), 1)
        self.assertTrue(any(w.category is datareader.MalformedLineWarning for w in caught))

    def test_literal_nan_becomes_a_real_nan(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]",
                   ["2026-09-11T10:00:00 nan", "2026-09-11T10:00:01 2.0"])
        frame = datareader.read_channel("ch", DAY, DAY, data_dir=self.root)
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
        found = datareader.find_files("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual([f.index for f in found], [0, 2, 10])

    def test_prefix_collision_does_not_leak_between_channels(self):
        write_file(self.root, DAY, "gem", "# Time v[V]", ["2026-09-11T10:00:00 1"])
        write_file(self.root, DAY, "gemtop", "# Time v[V]", ["2026-09-11T10:00:00 2"])
        found = datareader.find_files("gem", DAY, DAY, data_dir=self.root)
        self.assertEqual([f.name for f in found], ["20260911_gem.dat"])

    def test_units_convert_rescales_and_warns(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = datareader.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(frame["vmon"].tolist(), [100.0, 99500.0])
        self.assertEqual(datareader.units_of(frame), {"vmon": "V"})
        self.assertTrue(any(w.category is datareader.UnitMismatchWarning for w in caught))

    def test_units_raise_refuses_to_guess(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        with self.assertRaises(ValueError):
            datareader.read_channel("ch", DAY, DAY, data_dir=self.root, units="raise")

    def test_units_keep_tags_the_source(self):
        write_file(self.root, DAY, "ch", "# Time vmon[V]", ["2026-09-11T10:00:00 100.0"])
        write_file(self.root, DAY, "ch", "# Time vmon[kV]",
                   ["2026-09-11T11:00:00 99.5"], index=1)
        frame = datareader.read_channel("ch", DAY, DAY, data_dir=self.root, units="keep")
        self.assertEqual(frame["vmon"].tolist(), [100.0, 99.5])
        self.assertEqual(sorted(set(frame["source_file"])),
                         ["20260911_ch.dat", "20260911_ch_1.dat"])

    def test_incompatible_quantities_raise_even_when_converting(self):
        write_file(self.root, DAY, "ch", "# Time x[V]", ["2026-09-11T10:00:00 1.0"])
        write_file(self.root, DAY, "ch", "# Time x[A]",
                   ["2026-09-11T11:00:00 2.0"], index=1)
        with self.assertRaises(ValueError):
            datareader.read_channel("ch", DAY, DAY, data_dir=self.root)


class TestManyColumnsAndTextValues(unittest.TestCase):
    """Nothing is specific to two columns or to numeric values."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def test_many_columns_with_their_own_units(self):
        write_file(self.root, DAY, "envprobe",
                   "# Time pressure[mbar] temperature[C] humidity[%] flow[l/min]",
                   ["2026-09-11T10:00:00 1013.25 21.0 40.0 2.5",
                    "2026-09-11T10:00:01 1013.65 21.3 42.0 2.6"])
        frame = datareader.read_channel("env probe", DAY, DAY, data_dir=self.root)
        self.assertEqual(list(frame.columns),
                         ["pressure", "temperature", "humidity", "flow"])
        self.assertEqual(datareader.units_of(frame),
                         {"pressure": "mbar", "temperature": "C",
                          "humidity": "%", "flow": "l/min"})
        self.assertEqual(frame["flow"].tolist(), [2.5, 2.6])

    def test_one_column(self):
        write_file(self.root, DAY, "single", "# Time pressure[mbar]",
                   ["2026-09-11T10:00:00 1013.25"])
        frame = datareader.read_channel("single", DAY, DAY, data_dir=self.root)
        self.assertEqual(list(frame.columns), ["pressure"])

    def test_text_column_survives_instead_of_becoming_nan(self):
        write_file(self.root, DAY, "probe", "# Time temperature[C] state[]",
                   ["2026-09-11T10:00:00 21.0 OK",
                    "2026-09-11T10:00:01 22.0 NOT_READY"])
        frame = datareader.read_channel("probe", DAY, DAY, data_dir=self.root)
        self.assertEqual(frame["state"].tolist(), ["OK", "NOT_READY"])
        self.assertEqual(frame["temperature"].tolist(), [21.0, 22.0])

    def test_all_nan_column_stays_numeric(self):
        write_file(self.root, DAY, "probe", "# Time v[V]",
                   ["2026-09-11T10:00:00 nan", "2026-09-11T10:00:01 nan"])
        frame = datareader.read_channel("probe", DAY, DAY, data_dir=self.root)
        self.assertTrue(frame["v"].isna().all())
        self.assertEqual(frame["v"].dtype.kind, "f")

    def test_to_numpy_skips_text_columns(self):
        write_file(self.root, DAY, "probe", "# Time temperature[C] state[]",
                   ["2026-09-11T10:00:00 21.0 OK"])
        frame = datareader.read_channel("probe", DAY, DAY, data_dir=self.root)
        _, values, names = datareader.to_numpy(frame)
        self.assertEqual(names, ["temperature"])
        self.assertEqual(values.shape, (1, 1))

    def test_unparseable_timestamp_is_reported_not_dropped_quietly(self):
        # a value containing a space used to shift the columns and yield a NaT row
        write_file(self.root, DAY, "probe", "# Time temperature[C] state[]",
                   ["2026-09-11T10:00:00 21.0 OK",
                    "2026-09-11T10:00:01 22.0 NOT READY"])
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            frame = datareader.read_channel("probe", DAY, DAY, data_dir=self.root)
        self.assertEqual(len(frame), 1)
        self.assertTrue(any(w.category is datareader.MalformedLineWarning for w in caught))


class TestWriterQuotesNothing(unittest.TestCase):
    """channel.py must never emit a value containing the delimiter."""

    def test_whitespace_in_a_value_is_collapsed(self):
        import channel
        state = channel.ChannelState(
            "probe", ["temperature", "state"],
            thresholds={"temperature": 0.1, "state": 0},
            precisions={"temperature": 2}, units={"temperature": "C", "state": ""},
        )
        state.set_state({"temperature": 21.0, "state": "NOT READY"})
        row = state._state_to_row(state.current)
        self.assertEqual(row[1:], ["21.00", "NOT_READY"])
        self.assertTrue(all(" " not in token for token in row[1:]))

    def test_empty_value_does_not_collapse_to_nothing(self):
        import channel
        state = channel.ChannelState("probe", ["note"], thresholds={"note": 0})
        state.set_state({"note": ""})
        self.assertEqual(state._state_to_row(state.current)[1], "nan")


class TestChannelResolution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_file(self.root, DAY, "meshright", "# Time vmon[V]",
                   ["2026-09-11T10:00:00 1.0"])

    def test_display_name_slug_and_casing_all_resolve(self):
        for name in ("mesh right", "meshright", "MeshRight", "MESH RIGHT"):
            frame = datareader.read_channel(name, DAY, DAY, data_dir=self.root)
            self.assertEqual(len(frame), 1, name)

    def test_unknown_channel_raises_and_lists_what_exists(self):
        with self.assertRaises(FileNotFoundError) as context:
            datareader.read_channel("nope", DAY, DAY, data_dir=self.root)
        self.assertIn("meshright", str(context.exception))
        self.assertIn(self.root, str(context.exception))

    def test_list_channels(self):
        self.assertEqual(datareader.list_channels(DAY, DAY, data_dir=self.root), ["meshright"])


class TestDateRange(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        write_file(self.root, DAY, "ch", "# Time v[V]",
                   ["2026-09-11T08:00:00 1", "2026-09-11T20:00:00 2"])
        write_file(self.root, NEXT_DAY, "ch", "# Time v[V]", ["2026-09-12T08:00:00 3"])

    def test_range_spans_days(self):
        frame = datareader.read_channel("ch", DAY, NEXT_DAY, data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [1, 2, 3])

    def test_bare_end_date_includes_the_whole_day(self):
        frame = datareader.read_channel("ch", DAY, DAY, data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [1, 2])   # 20:00 must be included

    def test_times_narrow_the_range(self):
        frame = datareader.read_channel("ch", "2026-09-11 09:00", "2026-09-12 09:00",
                                    data_dir=self.root)
        self.assertEqual(frame["v"].tolist(), [2, 3])

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(ValueError):
            datareader.read_channel("ch", NEXT_DAY, DAY, data_dir=self.root)


class TestParseWhen(unittest.TestCase):
    def test_iso_forms(self):
        self.assertEqual(datareader.parse_when("2026-09-11"), dt.datetime(2026, 9, 11))
        self.assertEqual(datareader.parse_when("2026-09-11 13:05"), dt.datetime(2026, 9, 11, 13, 5))
        self.assertEqual(datareader.parse_when("2026-09-11T13:05:07"),
                         dt.datetime(2026, 9, 11, 13, 5, 7))

    def test_bare_date_end_of_day(self):
        stamp = datareader.parse_when("2026-09-11", end_of_day=True)
        self.assertEqual((stamp.hour, stamp.minute, stamp.second), (23, 59, 59))

    def test_a_date_with_a_time_ignores_end_of_day(self):
        self.assertEqual(datareader.parse_when("2026-09-11 13:05", end_of_day=True),
                         dt.datetime(2026, 9, 11, 13, 5))

    def test_keywords_and_offsets(self):
        self.assertEqual(datareader.parse_when("today").date(), dt.date.today())
        self.assertEqual(datareader.parse_when("yesterday").date(),
                         dt.date.today() - dt.timedelta(days=1))
        delta = dt.datetime.now() - datareader.parse_when("-2h")
        self.assertAlmostEqual(delta.total_seconds(), 7200, delta=5)


class TestToNumpy(unittest.TestCase):
    def test_shapes_and_dtypes(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        write_file(tmp.name, DAY, "ch", "# Time v[V] i[uA]",
                   ["2026-09-11T10:00:00 1.0 0.1", "2026-09-11T10:00:01 2.0 0.2"])
        frame = datareader.read_channel("ch", DAY, DAY, data_dir=tmp.name)
        seconds, values, names = datareader.to_numpy(frame)
        self.assertEqual(seconds.shape, (2,))
        self.assertEqual(values.shape, (2, 2))
        self.assertEqual(names, ["v", "i"])
        self.assertEqual(str(seconds.dtype), "float64")


class TestAgainstRepositoryData(unittest.TestCase):
    """Smoke test against whatever is really in data/, if anything."""

    def setUp(self):
        import channel
        if not datareader.list_channels("2000-01-01", "2100-01-01", data_dir=channel.DATA_DIR):
            self.skipTest("no recorded data in the repository's data/ directory")
        self.root = channel.DATA_DIR

    def test_every_channel_parses(self):
        names = datareader.list_channels("2000-01-01", "2100-01-01", data_dir=self.root)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name in names:
                frame = datareader.read_channel(name, "2000-01-01", "2100-01-01",
                                            data_dir=self.root)
                self.assertTrue(frame.index.is_monotonic_increasing, name)
                self.assertEqual(frame.index.isna().sum(), 0, name)


if __name__ == "__main__":
    unittest.main()
