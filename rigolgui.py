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
from channel import ChannelState
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

        channels_states = {}
        for name in channel_names:
            channels_states[name] = ChannelState(
                name,
                ["voltage", "current", "power", "state"],
                thresholds={"voltage": 0.05, "current": 0.01},
                precisions={"voltage": 2, "current": 2, "power": 2},
                units={"voltage": "V", "current": "A", "power": "W"},
                save_value={"voltage": True, "current": True, "power": False, "state": False},
            )

        super().__init__(
                        device=device,
                        channels_states=channels_states,
                        parent_frame=parent_frame,
                        logging_enabled=log,
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

        return main_frame
    
    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel states here. Widgets are updated by update_gui(), on the main thread.
        with self.device:
            for i, name in enumerate(self.channels_name):
                measurements = self.device.measure_all(i+1) # voltage, current, power. First channel in rigol is 1
                self.channels_state[name].set_state(
                    {   # keep this order in sync with value_names, above
                        "voltage": measurements.get("voltage", -1),
                        "current": measurements.get("current", -1),
                        "power": measurements.get("power", -1),
                        "state": self.device.get_output_state(i+1), # first channel in rigol is 1
                    }
                )

    def update_gui(self):
        for i, name in enumerate(self.channels_name):
            values = self.channels_state[name].get_values()
            self.voltage_labels[i].config(text=f"{values.get('voltage', -1):.3f} V")
            self.current_labels[i].config(text=f"{values.get('current', -1):.3f} A")
            self.power_labels[i].config(text=f"{values.get('power', -1):.3f} W")
            state = values.get("state", "---")
            self.state_labels[i].config(text=state, fg="green" if state == "ON" else "red")

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