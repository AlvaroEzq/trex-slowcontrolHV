from __future__ import annotations

import tkinter as tk
import argparse
import threading

CHANNEL_NAMES = ["BGA_Ar"]

from bgaClass import BGA244
from check import Check
from checkframe import ChecksFrame
from utilsgui import ToolTip
from devicegui import DeviceGUI

class BGA244GUI(DeviceGUI):
    """
    A GUI class for controlling the BGA244 device.

    Inherits from DeviceGUI and provides specific functionality for the BGA244 device.
    """

    def __init__(self, device, parent_frame=None, channels_names=None, log=True):
        if channels_names is None:
            channels_names = []

        self.channels_labels = []
        super().__init__(device, CHANNEL_NAMES, parent_frame,
                        logging_enabled=log,
                        channel_state_save_previous=False,
                        channel_state_diff_vmon=0.1,
                        channel_state_diff_imon=999,
                        channel_state_prec_vmon=3,
                        channel_state_prec_imon=0,
                        read_loop_time=10,
                        )
    
    def create_gui(self):
        self.main_frame = tk.LabelFrame(self.root, text="BGA244 Control", padx=10, pady=10, bd=4)
        self.main_frame.pack(fill="both", expand=True)
        
        self.channel_frame = self.create_channel_frame(self.main_frame, self.channels_name)
    
    def create_channel_frame(self, frame, channels_name):
        channel_frame = tk.Frame(frame)
        channel_frame.pack(fill="both", expand=True)

        row = 0
        for channel in channels_name:
            tk.Label(channel_frame, text=channel).grid(row=row, column=0, sticky="w")
            label = tk.Label(channel_frame, width=10, justify="center", text="-1")
            label.grid(row=row, column=1, padx=5, pady=5)
            self.channels_labels.append(label)
            row += 1

        return channel_frame
    
    def read_values(self):
        for i, channel in enumerate(self.channels_name):
            self.device.connect()
            ratio = self.device.get_ratio(primary_gas=True, unit='%')
            self.device.disconnect()

            self.channels_state[i].set_state(ratio, 0)
            self.channels_labels[i].config(text=f"{ratio:.3f}%")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGA244 GUI Control")
    parser.add_argument("--resource", type=str, required=True, help="Resource name for the BGA244 device")
    args = parser.parse_args()

    # Initialize the BGA244 device
    bga_device = BGA244(resource_name=args.resource)
    BGA244GUI(device=bga_device, channels_names=CHANNEL_NAMES)