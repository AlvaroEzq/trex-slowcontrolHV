import datetime as dt
import os
import logging
import queue
import threading
import requests
import json

import copy
import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

LOG_DIR = "logs"

def create_directory_recursive(path):
    try:
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"Error occurred while creating directory '{path}': {e}")

def get_path_from_date(dt_obj):
    return LOG_DIR + "/" + dt_obj.strftime("%Y/%m/%d")

def get_full_filename_from_date(dt_obj, suffix="", extension="dat"):
    path = get_path_from_date(dt_obj)
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
            f"{k}: {v} ({self.units.get(k, '')})".strip()
            for k, v in self.values.items()
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
    - threshold-based logging
    - CSV writing
    - immutable state snapshots
    """

    def __init__(self, channel_name, value_names, thresholds=None, precisions=None, units=None, save_value=None):

        self.name = channel_name
        self.value_names = value_names

        # Thresholds for deciding whether a value changed enough to trigger logging.
        # Example: { "vmon": 0.5, "imon": 0.01, "pressure": 0.1,}
        self.thresholds = thresholds or {}

        # Precision for file output (number of decimal places) for specific variables.Example:{"vmon": 1,"imon": 3,}
        self.precisions = precisions or {}
        
        # Units for display purposes. Example: {"vmon": "V", "imon": "A", "pressure": "mbar",}
        self.units = units or {}
        
        # flag to decide whether to save a specific variable (if None, all are saved). Example: {"vmon": True, "imon": True, "pressure": False,}
        self.save_value = save_value or {}

        # Initialize state snapshots
        self.current = State()
        self.previous = State()
        self.last_saved = State()
        
        self.lock = threading.Lock()

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
    # Logging
    # ========================================================
    def save_state(self, force=False, save_previous=True):
        with self.lock:
            if not (force or self.is_different()):
                return
            filename = get_full_filename_from_date(self.current.timestamp, suffix=self.name.replace(" ", ""))
            if self.last_saved != self.previous and save_previous:
                self.write_state_to_file(self.previous, filename, delimiter=' ')
            self.write_state_to_file(self.current, filename, delimiter=' ')
            self.last_saved = self.current

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

        row = [state.timestamp.strftime("%Y-%m-%d %H:%M:%S")]

        for key, value in state.values.items():
            if not self.save_value.get(key, True):
                continue
            precision = self.precisions.get(key)
            if (
                precision is not None
                and isinstance(value, (int, float))
            ):
                value = f"{value:.{precision}f}"
            row.append(value)

        return row
    
    def _state_to_str(self, state: State, delimiter=" "):
        row = self._state_to_row(state)
        if len(row) <= 1: # Only timestamp, no values
            return ""
        return delimiter.join(row)

    def _build_filename(self, directory):
        date_str = self.current.timestamp.strftime("%Y-%m-%d")
        safe_name = self.channel_name.replace(" ", "_")
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{date_str}_{safe_name}.csv"
    
    def write_state_to_file(self, state: State, filename: str, delimiter=' '):
        create_directory_recursive(filename)
        if not os.path.isfile(filename):
            try:
                # create the file if it does not exist
                header_str = self.file_header_str(delimiter=delimiter)
                if not header_str: # no values to write, skip creating the file
                    return
                with open(filename, 'w') as file:
                    file.write(self.file_header_str(delimiter=delimiter) + "\n")
                print("Writing to new file:", filename)
            except:
                print("Invalid file or directory:", filename)

        row_str = self._state_to_str(state, delimiter=delimiter) # empty string if only timestamp and no values to save
        if not row_str: # no values to write, skip writing the row
            return
        with open(filename, 'a') as file:
            file.write(row_str + "\n")


    def to_dict(self):
        return {
            "channel": self.channel_name,
            "current": self.current.to_dict(),
            "previous": self.previous.to_dict(),
            "last_saved": self.last_saved.to_dict(),
        }

    def __str__(self):
        return (
            f"{self.name} | "
            f"{self.current}"
        )