import datetime as dt
import os
import copy
import threading
from dataclasses import dataclass, field

def _default_data_dir():
    """
    Root directory for recorded channel values.

    Resolved as $TREX_HV_DATA if set, else the "data" directory next to this file.
    Deliberately NOT relative to the current working directory: that used to make
    launching the GUI from somewhere else silently start a second, separate data
    tree. Note this is only for recorded measurements; python logging of messages
    writes to LOG_DIR in logger.py.
    """
    return os.environ.get("TREX_HV_DATA") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"
    )

DATA_DIR = _default_data_dir()

def set_data_dir(path):
    """Override the recording root (used by the --data-dir command line option)."""
    global DATA_DIR
    DATA_DIR = os.path.abspath(os.path.expanduser(path))
    return DATA_DIR

def channel_slug(name):
    """Channel name as it appears in a filename, e.g. "mesh right" -> "meshright"."""
    return name.replace(" ", "")

def create_directory_recursive(path):
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"Error occurred while creating directory '{path}': {e}")

def get_record_dir_from_date(dt_obj):
    return DATA_DIR + "/" + dt_obj.strftime("%Y/%m/%d")

def get_record_filename_from_date(dt_obj, suffix="", extension="dat"):
    path = get_record_dir_from_date(dt_obj)
    return f"{path}/{dt_obj.strftime('%Y%m%d')}_{suffix}.{extension}"


# ============================================================
# Generic immutable state snapshot
# ============================================================

@dataclass(frozen=True)
class State:
    """
    Generic immutable snapshot of channel/device state.
    """
    timestamp: dt.datetime = field(default_factory=dt.datetime.now)
    values: dict = field(default_factory=dict)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            **self.values
        }

    def __str__(self):

        values_str = ", ".join(
            f"{k}: {v}" for k, v in self.values.items()
        )

        return f"{self.timestamp} | {values_str}"


# ============================================================
# Generic channel state manager
# ============================================================
class ChannelState:
    """
    Generic state manager for any device channel.

    Features:
    - current/previous/last_saved snapshots
    - generic variable support
    - threshold-based recording to file
    - immutable state snapshots
    """

    def __init__(self, channel_name, value_names, thresholds=None, precisions=None, units=None, save_value=None):

        self.name = channel_name
        self.value_names = value_names

        # Thresholds for deciding whether a value changed enough to trigger a recording.
        # Example: { "vmon": 0.5, "imon": 0.01, "pressure": 0.1,}
        self.thresholds = thresholds or {}

        # Precision for file output (number of decimal places) for specific variables.Example:{"vmon": 1,"imon": 3,}
        self.precisions = precisions or {}
        
        # Units for display purposes. Example: {"vmon": "V", "imon": "A", "pressure": "mbar",}
        self.units = units or {}
        
        # flag to decide whether to save a specific variable (if None, all are saved). Example: {"vmon": True, "imon": True, "pressure": False,}
        self.save_value = save_value or {}

        # A row is only written when is_different() says something moved, and it only
        # looks at keys present in thresholds. A magnitude that is saved to file but
        # has no threshold therefore never triggers a write of its own, so its column
        # only updates when some other magnitude happens to move.
        unwatched = [
            key for key in self.value_names
            if self.save_value.get(key, True) and key not in self.thresholds
        ]
        if unwatched:
            print(
                f"Warning: channel '{self.name}' saves {unwatched} to file but has no"
                f" threshold for them, so a change in those values alone will not be"
                f" recorded. Add them to 'thresholds' to record them."
            )

        # Initialize state snapshots
        self.current = State()
        self.previous = State()
        self.last_saved = State()
        
        self.lock = threading.Lock()       # guards the state snapshots only
        self.file_lock = threading.Lock()  # serializes writes to the channel file

        # Output file resolved for the current (base filename, header) pair, so the
        # header only has to be re-checked on a day rollover or a schema change.
        self._active_schema = None
        self._active_path = None

    def set_state(self, values: dict):
        # check that values has the expected keys
        for key in self.value_names:
            if key not in values:
                raise ValueError(f"Missing value for '{key}' in channel '{self.name}'")

        with self.lock:
            self.previous = self.current
            self.current = State(values=copy.deepcopy(values))
    
    def get_value(self, key, default=None):
        with self.lock:
            return self.current.get(key, default)
    
    def get_state(self):
        with self.lock:
            return self.current
    
    def get_values(self):
        with self.lock:
            return self.current.values.copy()

    def is_different(self):
        for key, threshold in self.thresholds.items():
            current_value = self.current.get(key)
            saved_value = self.last_saved.get(key)

            if current_value is None and saved_value is None:
                continue
            
            if current_value is not None and saved_value is None:
                return True

            # numeric threshold comparison
            if isinstance(current_value, (int, float)):
                if abs(current_value - saved_value) >= threshold:
                    return True
            # non-numeric direct comparison
            else:
                if current_value != saved_value:
                    return True

        return False

    # ========================================================
    # Recording to file
    # ========================================================
    def save_state(self, force=False, save_previous=True):
        # Only the state snapshots are touched under self.lock. File I/O (and the
        # print() it may do, which is redirected to a Tk widget and therefore blocks
        # until the GUI main thread services it) must stay outside the lock, or the
        # main thread deadlocks against this one while waiting in get_values().
        with self.lock:
            if not (force or self.is_different()):
                return
            current = self.current
            previous = self.previous
            write_previous = save_previous and self.last_saved != previous
            self.last_saved = current

        filename = get_record_filename_from_date(current.timestamp, suffix=channel_slug(self.name))
        with self.file_lock:
            if write_previous:
                self.write_state_to_file(previous, filename, delimiter=' ')
            self.write_state_to_file(current, filename, delimiter=' ')

    def file_header_row(self):
        header = ["Time"]
        for key in self.value_names:
            if not self.save_value.get(key, True):
                continue
            header.append(f"{key}[{self.units.get(key, '')}]")
        return header
        
    def file_header_str(self, delimiter=","):
        row = self.file_header_row()
        if len(row) <= 1: # Only timestamp, no values
            return ""
        return delimiter.join(row)

    def _state_to_row(self, state: State):
        # Iterate value_names, the same list file_header_row() uses, so a value can
        # never end up under the wrong column. Iterating state.values instead would
        # follow whatever order read_values() happened to build its dict in.
        row = [state.timestamp.strftime("%Y-%m-%d %H:%M:%S")]

        for key in self.value_names:
            if not self.save_value.get(key, True):
                continue
            value = state.get(key, "nan")
            precision = self.precisions.get(key)
            if (
                precision is not None
                and isinstance(value, (int, float))
            ):
                value = f"{value:.{precision}f}"
            row.append(str(value))

        return row

    def _state_to_str(self, state: State, delimiter=" "):
        if not state.values: # empty snapshot, e.g. before the first read
            return ""
        row = self._state_to_row(state)
        if len(row) <= 1: # Only timestamp, no values
            return ""
        return delimiter.join(row)

    def _resolve_filename(self, base_filename: str, header_str: str):
        """
        Return the file to append to for the given header.

        The header is only written when a file is created, so if the recorded
        magnitudes change (save_value, units, value_names or their order), appending
        to an existing file would file the new rows under a stale header. Instead,
        roll over to "<base>_1.dat", "<base>_2.dat", ... until a file whose header
        matches (or a free name) is found. The previous day's data stays readable and
        no rows are ever mislabelled.
        """
        if (base_filename, header_str) == self._active_schema:
            return self._active_path # already resolved for this file and header

        root, extension = os.path.splitext(base_filename)
        path, index = base_filename, 0
        while os.path.isfile(path):
            with open(path) as file:
                existing_header = file.readline().rstrip("\n")
            # an empty leftover file is reusable: write_state_to_file re-writes its header
            if existing_header in (header_str, ""):
                break
            index += 1
            path = f"{root}_{index}{extension}"

        self._active_schema = (base_filename, header_str)
        self._active_path = path
        return path

    def write_state_to_file(self, state: State, filename: str, delimiter=' '):
        header_str = self.file_header_str(delimiter=delimiter)
        if not header_str: # no values to save for this channel, skip the file entirely
            return
        row_str = self._state_to_str(state, delimiter=delimiter)
        if not row_str: # nothing to write for this state
            return

        create_directory_recursive(filename)
        filename = self._resolve_filename(filename, header_str)
        try:
            if not os.path.isfile(filename) or os.path.getsize(filename) == 0:
                with open(filename, 'w') as file:
                    file.write(header_str + "\n")
                print("Writing to new file:", filename)
            with open(filename, 'a') as file:
                file.write(row_str + "\n")
        except OSError as e:
            print(f"Could not write to file {filename}: {e}")


    def to_dict(self):
        return {
            "channel": self.name,
            "current": self.current.to_dict(),
            "previous": self.previous.to_dict(),
            "last_saved": self.last_saved.to_dict(),
        }

    def __str__(self):
        return (
            f"{self.name} | "
            f"{self.current}"
        )