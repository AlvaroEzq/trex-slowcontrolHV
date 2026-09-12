"""
Read back the channel values recorded by the GUIs.

The recording side lives in channel.py, which writes one whitespace-delimited file
per channel per day under DATA_DIR:

    data/2026/09/11/20260911_gemtop.dat
        # Time vmon[V] imon[uA]
        2026-09-11T13:05:39 100.1 0.010

This module turns a channel name and a time range into a single pandas DataFrame,
gathering the day files across the range and the _1 / _2 siblings that channel.py
creates when the recorded magnitudes change mid-day.

    import datareader
    df = datareader.read_channel("cathode", "2026-09-01", "2026-09-11")
    df["vmon"].plot()

It is also a command line tool, for the gnuplot / awk / grep workflow:

    python3 datareader.py list
    python3 datareader.py info -c "gem top" --from -7d
    python3 datareader.py dump -c "gem top" --from -7d --epoch | gnuplot ...
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import sys
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

import channel

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S"   # what channel.py writes; older files used a space

# A day file may be followed by _1, _2, ... when the header changed mid-day.
SIBLING_SUFFIX_RE = re.compile(r"^(_(\d+))?$")
HEADER_TOKEN_RE = re.compile(r"^(?P<key>.*?)\[(?P<unit>.*)\]$")

SI_PREFIXES = {
    "p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3,
    "": 1.0, "k": 1e3, "M": 1e6, "G": 1e9,
}


class UnitMismatchWarning(UserWarning):
    """Sibling files of the same channel were recorded in different units."""


class MalformedLineWarning(UserWarning):
    """A line could not be parsed and was skipped."""


@dataclass(frozen=True)
class RecordFile:
    """One recorded file on disk, with its header already parsed."""
    path: str
    day: dt.date
    index: int              # 0 for <base>.dat, 1 for _1.dat, ...
    columns: tuple          # ("vmon", "imon")
    units: dict             # {"vmon": "V", "imon": "uA"}

    @property
    def name(self):
        return os.path.basename(self.path)


# ------------------------------------------------------------------
# Paths and headers
# ------------------------------------------------------------------

def data_root(data_dir=None):
    """Resolve the recording root: explicit argument, else channel.DATA_DIR."""
    if data_dir:
        return os.path.abspath(os.path.expanduser(data_dir))
    return channel.DATA_DIR


def parse_header(line):
    """
    "# Time vmon[V] imon[uA]" -> (["vmon", "imon"], {"vmon": "V", "imon": "uA"})

    The leading "# " is optional: files recorded before it was introduced do not
    have it. A column with no [unit] is kept with an empty unit.
    """
    tokens = line.lstrip("#").strip().split()
    if not tokens:
        return [], {}
    columns, units = [], {}
    for token in tokens[1:]:  # tokens[0] is the "Time" column
        match = HEADER_TOKEN_RE.match(token)
        if match:
            key, unit = match.group("key"), match.group("unit")
        else:
            key, unit = token, ""
        columns.append(key)
        units[key] = unit
    return columns, units


def _read_header(path):
    with open(path) as file:
        return parse_header(file.readline())


def _subdirectories(path):
    try:
        return [name for name in os.listdir(path)
                if os.path.isdir(os.path.join(path, name))]
    except OSError:
        return []


def _iter_day_dirs(root, start, end):
    """
    (date, directory) for every recorded day in [start, end] that exists on disk.

    Walks the YYYY/MM/DD tree rather than stepping one day at a time, so the cost
    follows how much data there is rather than how wide the range is. Asking for
    everything since 2020 should not cost two thousand directory lookups.
    """
    first, last = start.date(), end.date()
    for year in sorted(_subdirectories(root)):
        if not year.isdigit() or not (first.year <= int(year) <= last.year):
            continue
        year_path = os.path.join(root, year)
        for month in sorted(_subdirectories(year_path)):
            if not month.isdigit():
                continue
            month_path = os.path.join(year_path, month)
            for day in sorted(_subdirectories(month_path)):
                if not day.isdigit():
                    continue
                try:
                    date = dt.date(int(year), int(month), int(day))
                except ValueError:
                    continue
                if first <= date <= last:
                    yield date, os.path.join(month_path, day)


def find_files(channel_name, start=None, end=None, data_dir=None):
    """Every recorded file for a channel in [start, end], chronological."""
    root = data_root(data_dir)
    start, end = _resolve_range(start, end)
    slug = _resolve_slug(channel_name, start, end, data_dir)

    found = []
    for day, directory in _iter_day_dirs(root, start, end):
        stem = day.strftime("%Y%m%d") + "_" + slug
        for path in glob.glob(os.path.join(directory, stem + "*.dat")):
            # the glob is a prefix match, so "gem" would also pick up "gemtop":
            # only a bare name or an _N sibling of this exact slug counts
            suffix = os.path.basename(path)[len(stem):-len(".dat")]
            match = SIBLING_SUFFIX_RE.match(suffix)
            if not match:
                continue
            columns, units = _read_header(path)
            found.append(RecordFile(
                path=path, day=day, index=int(match.group(2) or 0),
                columns=tuple(columns), units=units,
            ))

    # sort siblings numerically: "_10" would come before "_2" as a string
    found.sort(key=lambda f: (f.day, f.index))
    return found


def _resolve_slug(channel_name, start, end, data_dir):
    """
    Filename slug for a channel name, verified against what is on disk.

    Accepts the display name ("mesh right"), the slug ("meshright") and any
    casing. Raises rather than returning nothing, so a typo or a wrong data root
    never looks like "this channel recorded no data".
    """
    slug = channel.channel_slug(channel_name)
    available = list_channels(start, end, data_dir)
    if slug in available:
        return slug
    for candidate in available:
        if candidate.lower() == slug.lower():
            return candidate
    raise FileNotFoundError(
        f"no recorded files for channel {channel_name!r} (looked for {slug!r}) "
        f"under {data_root(data_dir)}.\nChannels recorded in that range: "
        + (", ".join(available) if available else "(none)")
    )


def list_channels(start=None, end=None, data_dir=None):
    """
    Channel slugs present on disk in [start, end].

    These are filename slugs, so "mesh right" appears as "meshright". Either
    spelling can be handed back to read_channel.
    """
    root = data_root(data_dir)
    start, end = _resolve_range(start, end)
    names = set()
    for day, directory in _iter_day_dirs(root, start, end):
        prefix = day.strftime("%Y%m%d") + "_"
        for path in glob.glob(os.path.join(directory, prefix + "*.dat")):
            stem = os.path.basename(path)[len(prefix):-len(".dat")]
            names.add(re.sub(r"_\d+$", "", stem))
    return sorted(names)


# ------------------------------------------------------------------
# Units
# ------------------------------------------------------------------

def _split_unit(unit):
    """"kV" -> ("V", 1000.0). An unprefixed or unknown unit scales by 1."""
    if len(unit) > 1 and unit[0] in SI_PREFIXES and unit[0] != "":
        return unit[1:], SI_PREFIXES[unit[0]]
    return unit, 1.0


def unit_factor(source, target):
    """
    Multiplier converting a value in `source` units to `target` units.

    Raises ValueError if the two are not the same quantity, e.g. V and A.
    """
    if source == target:
        return 1.0
    source_base, source_scale = _split_unit(source)
    target_base, target_scale = _split_unit(target)
    if source_base != target_base:
        raise ValueError(f"cannot convert {source!r} to {target!r}")
    return source_scale / target_scale


# ------------------------------------------------------------------
# Reading
# ------------------------------------------------------------------

def _to_numeric_if_it_is(series):
    """
    Convert a column to float, unless it is text.

    Most recorded magnitudes are numeric and the literal "nan" channel.py writes
    for a missing value has to become a real NaN. But a channel may record a
    status word, and coercing that to NaN would throw the column away, so a
    column that holds no numbers at all is kept as text.
    """
    converted = pd.to_numeric(series, errors="coerce")
    if converted.notna().any():
        return converted
    if series.astype(str).str.lower().isin(["nan", ""]).all():
        return converted        # genuinely all missing
    return series               # text column, e.g. a status word


def read_file(record_file, columns=None):
    """
    One recorded file, in the units it was written in.

    Returns a DataFrame indexed by timestamp. Rows are parsed individually so a
    file spanning the timestamp format change, or ending in a half-written line
    from a crash, still reads.
    """
    if isinstance(record_file, str):
        cols, units = _read_header(record_file)
        record_file = RecordFile(path=record_file, day=dt.date.min, index=0,
                                 columns=tuple(cols), units=units)

    width = len(record_file.columns)
    stamps, rows, malformed = [], [], 0

    with open(record_file.path) as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = line.split()
            if not tokens[0][:1].isdigit():
                continue    # header line, with or without the "# " prefix
            if len(tokens) == width + 2:        # legacy "YYYY-MM-DD HH:MM:SS"
                stamp, values = tokens[0] + "T" + tokens[1], tokens[2:]
            elif len(tokens) == width + 1:      # ISO "YYYY-MM-DDTHH:MM:SS"
                stamp, values = tokens[0], tokens[1:]
            else:
                malformed += 1
                continue
            stamps.append(stamp)
            rows.append(values)

    frame = pd.DataFrame(rows, columns=list(record_file.columns))
    for column in frame.columns:
        frame[column] = _to_numeric_if_it_is(frame[column])
    frame.index = pd.to_datetime(pd.Series(stamps, dtype="object"), errors="coerce")
    frame.index.name = "Time"

    # a row whose token count matched but whose timestamp does not parse is still
    # malformed; dropping it quietly would lose data without saying so
    unparseable = int(frame.index.isna().sum())
    if unparseable:
        malformed += unparseable
        frame = frame[frame.index.notna()]

    if malformed:
        warnings.warn(
            f"{record_file.path}: skipped {malformed} malformed line(s)",
            MalformedLineWarning, stacklevel=2,
        )

    if columns:
        keep = [c for c in columns if c in frame.columns]
        frame = frame[keep]
    frame.attrs["units"] = {c: record_file.units.get(c, "") for c in frame.columns}
    return frame


def read_channel(channel_name, start=None, end=None, data_dir=None,
                 columns=None, units="convert"):
    """
    All values recorded for one channel in [start, end], as a DataFrame.

    Indexed by timestamp, one float column per recorded magnitude, with the units
    in df.attrs["units"] (read them with units_of(), .attrs does not survive every
    pandas operation).

    units:
      "convert" - rescale siblings to the units of the first file, warning about
                  each conversion. Raises if the quantities differ (V vs A).
      "raise"   - any disagreement between siblings is an error.
      "keep"    - no conversion; adds a source_file column so rows can be split.
      {"vmon": "V"} - convert to these units explicitly.
    """
    files = find_files(channel_name, start, end, data_dir)

    frames = []
    target_units = dict(units) if isinstance(units, dict) else {}

    for record_file in files:
        frame = read_file(record_file, columns=columns)
        file_units = frame.attrs["units"]

        for column, unit in file_units.items():
            target = target_units.setdefault(column, unit)
            if unit == target:
                continue
            if units == "keep":
                continue
            if units == "raise":
                raise ValueError(
                    f"{record_file.name} records {column} in {unit!r}, but "
                    f"{files[0].name} uses {target!r}"
                )
            factor = unit_factor(unit, target)   # ValueError if not the same quantity
            frame[column] = frame[column] * factor
            warnings.warn(
                f"{record_file.name}: {column} recorded in {unit!r}, scaled by "
                f"{factor:g} to match {target!r}",
                UnitMismatchWarning, stacklevel=2,
            )

        if units == "keep":
            frame["source_file"] = record_file.name
        frames.append(frame)

    combined = pd.concat(frames).sort_index(kind="stable")   # keeps file order within a timestamp
    start, end = _resolve_range(start, end)
    combined = combined.loc[(combined.index >= start) & (combined.index <= end)]
    combined.attrs["units"] = target_units
    combined.attrs["files"] = [f.path for f in files]
    return combined


def read_channels(channels, start=None, end=None, **kwargs):
    """read_channel for several channels: {name: DataFrame}."""
    return {name: read_channel(name, start, end, **kwargs) for name in channels}


def units_of(frame):
    """The units of a frame returned by read_channel."""
    return dict(frame.attrs.get("units", {}))


def to_numpy(frame):
    """
    (timestamps as unix seconds, values as a 2-D array, column names).

    For plain numpy and for feeding ROOT's TGraph.
    """
    seconds = pd.DatetimeIndex(frame.index).astype("int64") / 1e9
    columns = [c for c in frame.columns
               if c != "source_file" and pd.api.types.is_numeric_dtype(frame[c])]
    return (
        np.asarray(seconds, dtype="float64"),
        frame[columns].to_numpy(dtype="float64"),
        columns,
    )


# ------------------------------------------------------------------
# Time parsing
# ------------------------------------------------------------------

def parse_when(text, end_of_day=False):
    """
    A point in time from the command line.

    Accepts ISO ("2026-09-11", "2026-09-11 13:00", "2026-09-11T13:00:00"), the
    words now / today / yesterday, and offsets from now like -7d, -12h, -30m.
    A bare date means the start of that day, or the end of it if end_of_day.
    """
    if text is None:
        return None
    if isinstance(text, dt.datetime):
        return text
    if isinstance(text, dt.date):
        text = text.isoformat()

    text = text.strip()
    now = dt.datetime.now()
    lowered = text.lower()

    if lowered == "now":
        return now
    if lowered in ("today", "yesterday"):
        day = now.date() - dt.timedelta(days=1 if lowered == "yesterday" else 0)
        return _day_bound(day, end_of_day)

    match = re.fullmatch(r"([-+]?\d+)\s*([smhdw])", lowered)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
        return now + dt.timedelta(seconds=amount * seconds)

    stamp = dt.datetime.fromisoformat(text)
    if ":" not in text:      # a bare date carries no time of day
        return _day_bound(stamp.date(), end_of_day)
    return stamp


def _day_bound(day, end_of_day):
    if end_of_day:
        return dt.datetime.combine(day, dt.time(23, 59, 59, 999999))
    return dt.datetime.combine(day, dt.time())


def _resolve_range(start, end):
    """Default to today so far."""
    start = parse_when(start) if start is not None else _day_bound(dt.date.today(), False)
    end = parse_when(end, end_of_day=True) if end is not None else dt.datetime.now()
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    return start, end


# ------------------------------------------------------------------
# Command line
# ------------------------------------------------------------------

def _cmd_list(args):
    names = list_channels(args.start, args.end, args.data_dir)
    if not names:
        print(f"no recorded channels under {data_root(args.data_dir)} in that range",
              file=sys.stderr)
        return 1
    for name in names:
        print(name)
    return 0


def _cmd_info(args):
    files = find_files(args.channel, args.start, args.end, args.data_dir)
    print(f"root: {data_root(args.data_dir)}")
    total = 0
    for record_file in files:
        frame = read_file(record_file)
        total += len(frame)
        span = f"{frame.index.min()} .. {frame.index.max()}" if len(frame) else "(empty)"
        units = " ".join(f"{c}[{record_file.units.get(c, '')}]" for c in record_file.columns)
        print(f"  {record_file.name}  {len(frame):6d} rows  {units}  {span}")
    print(f"total: {total} rows in {len(files)} file(s)")

    frame = read_channel(args.channel, args.start, args.end,
                         data_dir=args.data_dir, units=args.units)
    if len(frame) > 1:
        gaps = frame.index.to_series().diff().dropna()
        print(f"largest gap between rows: {gaps.max()}")
    return 0


def _cmd_dump(args):
    frame = read_channel(args.channel, args.start, args.end, data_dir=args.data_dir,
                         columns=args.columns, units=args.units)
    units = units_of(frame)
    separator = "," if args.csv else " "

    out = open(args.output, "w") if args.output else sys.stdout
    try:
        if not args.no_header:
            names = ["Epoch" if args.epoch else "Time"] \
                + [f"{c}[{units.get(c, '')}]" for c in frame.columns]
            prefix = "" if args.csv else "# "
            print(prefix + separator.join(names), file=out)
        for stamp, row in frame.iterrows():
            when = f"{stamp.timestamp():.0f}" if args.epoch else stamp.strftime(TIMESTAMP_FORMAT)
            print(separator.join([when] + [_format(v) for v in row]), file=out)
    finally:
        if args.output:
            out.close()
    return 0


def _format(value):
    if isinstance(value, float) and value != value:   # NaN
        return "nan"
    return f"{value:g}" if isinstance(value, float) else str(value)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read back channel values recorded by the slow control GUIs.")
    parser.add_argument("--data-dir", help="recording root (default: $TREX_SC_DATA, "
                                           "else the data directory next to the code)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_range(sub):
        sub.add_argument("--from", dest="start", default=None,
                         help="start; ISO date/time, now, today, yesterday, or -7d (default: today)")
        sub.add_argument("--to", dest="end", default=None,
                         help="end, same formats (default: now)")

    listing = subparsers.add_parser("list", help="channels present on disk")
    add_range(listing)
    listing.set_defaults(func=_cmd_list)

    info = subparsers.add_parser("info", help="files, row counts, units and gaps")
    info.add_argument("-c", "--channel", required=True)
    info.add_argument("--units", default="convert", help="convert (default), keep or raise")
    add_range(info)
    info.set_defaults(func=_cmd_info)

    dump = subparsers.add_parser("dump", help="print a time range")
    dump.add_argument("-c", "--channel", required=True)
    dump.add_argument("--columns", default=None,
                      help="comma separated subset, e.g. vmon,imon")
    dump.add_argument("--units", default="convert", help="convert (default), keep or raise")
    dump.add_argument("--csv", action="store_true", help="comma separated, uncommented header")
    dump.add_argument("--epoch", action="store_true", help="unix seconds instead of a timestamp")
    dump.add_argument("--no-header", action="store_true")
    dump.add_argument("-o", "--output", default=None, help="write to a file instead of stdout")
    add_range(dump)
    dump.set_defaults(func=_cmd_dump)

    args = parser.parse_args(argv)
    if getattr(args, "columns", None):
        args.columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
