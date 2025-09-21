from __future__ import annotations

import tkinter as tk
import argparse

CHANNEL_NAMES = [
                'Channel 1',
                'Channel 2',
                'Channel 3',
                ]

CHANNEL_NAMES_LEFT = [
                'Left 1',
                'Left 2',
                ]

CHANNEL_NAMES_RIGHT = [
                'Right 1',
                'Right 2',
                'TCM',
                ]

from rigolClass import RigolPowerSupply
from check import Check
from checkframe import ChecksFrame
from utilsgui import ToolTip
from devicegui import DeviceGUI

class RigolGUI(DeviceGUI):
    """
    A GUI class for controlling the Rigol device.

    Inherits from DeviceGUI and provides specific functionality for the BGA244 device.
    """

    def __init__(self, device, parent_frame=None, channel_names=None, log=True):
        if channel_names is None:
            channel_names = CHANNEL_NAMES

        #self.channels_labels = []
        self.state_labels = []
        self.voltage_labels = []
        self.current_labels = []
        self.power_labels = []

        super().__init__(device, channel_names, parent_frame,
                        logging_enabled=log,
                        channel_state_save_previous=False,
                        channel_state_diff_vmon=0.05,
                        channel_state_diff_imon=0.01,
                        channel_state_prec_vmon=2,
                        channel_state_prec_imon=2,
                        read_loop_time=1,
                        )
    
    def create_gui(self):
        start_mainloop = False
        if self.root is None:
            self.root = tk.Tk()
            self.root.title("Rigol Monitor GUI")
            start_mainloop = True

        self.main_frame = tk.LabelFrame(self.root, text=f"{self.device.name}", font=("", 16), padx=10, pady=10, labelanchor="n", bd=4)
        self.main_frame.pack(fill="both", expand=True)
        
        self.main_frame = self.create_main_frame(self.main_frame, self.channels_name)

        if start_mainloop:
            self.root.mainloop()
    
    def create_main_frame(self, frame, channels_name):
        main_frame = tk.Frame(frame)
        main_frame.pack(fill="both", expand=True)

        for n, channel in enumerate(channels_name):
            channel_frame = tk.LabelFrame(main_frame, text=channel)
            channel_frame.grid(row=1, column=n, sticky="w")
            row = 0
            
            # row 0: state
            state_label = tk.Label(channel_frame, width=10, justify="center", text="---")
            state_label.grid(row=0, column=0, padx=5, pady=5)
            button_on = tk.Button(channel_frame, text="ON", width=5, command=lambda ch=channel: self.issue_command(self.turn_on_channel, ch))
            button_on.grid(row=0, column=1, padx=0)
            button_off = tk.Button(channel_frame, text="OFF", width=5, command=lambda ch=channel: self.issue_command(self.turn_off_channel, ch))
            button_off.grid(row=0, column=2, padx=0)
            
            #row 1: values
            voltage_label = tk.Label(channel_frame, text='-1')
            voltage_label.grid(row=1, column=0, padx=5, pady=5)
            current_label = tk.Label(channel_frame, text='-1')
            current_label.grid(row=1, column=1, padx=5, pady=5)
            power_label = tk.Label(channel_frame, text='-1')
            power_label.grid(row=1, column=2, padx=5, pady=5)
            
            self.state_labels.append(state_label)
            self.voltage_labels.append(voltage_label)
            self.current_labels.append(current_label)
            self.power_labels.append(power_label)
            row += 1

        return channel_frame
    
    def read_values(self):
        with self.device:
            #ratio = self.device.get_ratio(primary_gas=True, unit='%')

            for i, channel in enumerate(self.channels_name):
                measurements = self.device.measure_all(i+1) # voltage, current, power. First channel in rigol is 1
                voltage = measurements.get("voltage", -1)
                current = measurements.get("current", -1)
                power = measurements.get("power", -1)
                state = self.device.get_output_state(i+1) # first channel in rigol is 1
                self.channels_state[i].set_state(voltage, current)
                self.voltage_labels[i].config(text=f"{voltage:.3f} V")
                self.current_labels[i].config(text=f"{current:.3f} A")
                self.power_labels[i].config(text=f"{power:.3f} W")
                self.state_labels[i].config(text=state)
                if state == "ON":
                    self.state_labels[i].config(fg="green")
                else:
                    self.state_labels[i].config(fg="red")

    def turn_on_channel(self, channel_name):
        if channel_name not in self.channels_name:
            print(f"Channel {channel_name} not found.")
            return
        channel_index = self.channels_name.index(channel_name)+1
        with self.device:
            self.device.turn_on_channel(channel_index)
    
    def turn_off_channel(self, channel_name):
        if channel_name not in self.channels_name:
            print(f"Channel {channel_name} not found.")
            return
        channel_index = self.channels_name.index(channel_name)+1
        with self.device:
            self.device.turn_off_channel(channel_index)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGA244 GUI Control")
    parser.add_argument("--resource", type=str, help="Resource name for the BGA244 device")
    parser.add_argument("--test", action="store_true", help="Use a simulated device for testing")
    args = parser.parse_args()

    if args.test:
        from simulators import RigolSimulator
        print("Using Rigol Simulator")
        rigol_device = RigolSimulator()
    else:
        # Initialize the Rigol power supply
        if args.resource is None:
            print("Please provide a resource name using --resource")
            exit(1)
        rigol_device = RigolPowerSupply(resource_name=args.resource)
    
    RigolGUI(device=rigol_device, channel_names=CHANNEL_NAMES)