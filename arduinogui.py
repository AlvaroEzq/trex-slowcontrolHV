from __future__ import annotations

import tkinter as tk
import argparse

CHANNEL_NAMES = ["LSC", "Unizar"]

# The Arduino reads the alarms as digital signals: 0 is the quiet state, 1 is the
# alarm being raised. Anything else means the reading itself failed.
SIGNAL_DISPLAY = {
    0: ("OK", "green"),
    1: ("ALARM", "red"),
}
SIGNAL_DISPLAY_UNKNOWN = ("NO DATA", "orange")

from arduino import ArduinoReader
from channel import ChannelState
from check import Check
from checkframe import ChecksFrame
from utilsgui import ToolTip
from devicegui import DeviceGUI

class ArduinoGUI(DeviceGUI):
    """
    A GUI class for monitoring the digital safety alarm signals read by the Arduino.

    Inherits from DeviceGUI and provides specific functionality for the Arduino device.
    """

    def __init__(self, device, parent_frame=None, channel_names=None, log=True):
        if channel_names is None:
            channel_names = CHANNEL_NAMES

        self.channels_labels = []

        channels_states = {}
        for name in channel_names:
            channels_states[name] = ChannelState(
                name,
                ["signal"],
                thresholds={"signal": 0.5},  # digital signal: any 0 <-> 1 transition is logged
                precisions={"signal": 0},
                units={"signal": ""},
                save_value={"signal": True},
            )

        super().__init__(
                        device=device,
                        channels_states=channels_states,
                        parent_frame=parent_frame,
                        logging_enabled=log,
                        read_loop_time=10,
                        )

    def create_gui(self):
        self.main_frame = tk.LabelFrame(self.root, text="Arduino Control", padx=10, pady=10, bd=4)
        self.main_frame.pack(fill="both", expand=True)

        self.channel_frame = self.create_channel_frame(self.main_frame, self.channels_name)

    def create_channel_frame(self, frame, channels_name):
        channel_frame = tk.Frame(frame)
        channel_frame.pack(fill="both", expand=True)

        row = 0
        for channel in channels_name:
            tk.Label(channel_frame, text=channel).grid(row=row, column=0, sticky="w")
            label = tk.Label(channel_frame, width=10, justify="center",
                             text=SIGNAL_DISPLAY_UNKNOWN[0], fg=SIGNAL_DISPLAY_UNKNOWN[1])
            label.grid(row=row, column=1, padx=5, pady=5)
            self.channels_labels.append(label)
            row += 1

        return channel_frame

    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel states here. Widgets are updated by update_gui(), on the main thread.
        with self.device:
            # both signals come from the same serial line, so read them in one go
            # instead of consuming a different line per channel
            signals = self.device.get_both()
            for i, name in enumerate(self.channels_name):
                value = signals[i] if signals is not None and i < len(signals) else -1
                self.channels_state[name].set_state({"signal": value})

    def update_gui(self):
        for i, name in enumerate(self.channels_name):
            value = self.channels_state[name].get_value("signal", -1)
            text, color = SIGNAL_DISPLAY.get(value, SIGNAL_DISPLAY_UNKNOWN)
            self.channels_labels[i].config(text=text, fg=color)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arduino GUI Control")
    parser.add_argument("--port", type=str, default="/dev/ttyACM0", help="Serial port for the Arduino device")
    args = parser.parse_args()

    # Initialize the Arduino device
    arduino_device = ArduinoReader(port=args.port)
    ArduinoGUI(device=arduino_device, channel_names=CHANNEL_NAMES)
