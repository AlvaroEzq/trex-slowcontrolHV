from __future__ import annotations

import tkinter as tk
import threading
import queue
import time
import argparse

import hvps

CHANNEL_NAMES = {0: "mesh right", 1: "mesh left", 2: "gem top", 3: "gem bottom"}

from check import Check
from checkframe import ChecksFrame
from tooltip import ToolTip

import requests
import json
def send_slack_message(message:str):
    #### webhook to Alvaro chat
    # webhook_url = ""
    #### webhook to trex-operations channel
    webhook_url = ""

    slack_data = {'text': message}
    try:
        requests.post(webhook_url, data=json.dumps(slack_data), headers={'Content-Type': 'application/json'})
    except Exception as e:
        print(e)

class CaenHVPSGUI:
    def __init__(self, module, channel_names=None, checks=None, parent_frame=None, silence=False):
        if channel_names is None:
            channel_names = {}
        if checks is None:
            checks = {}

        self.channel_vars = None
        self.set_buttons = None
        self.turn_buttons = None
        self.state_tooltips = None
        self.state_indicators = None
        self.imon_labels = None
        self.vmon_labels = None
        self.vset_entries = None
        self.vset_labels = None
        self.checks = checks
        self.checks_vars = None
        self.checks_checkboxes = None

        self.alarm_frame = None
        self.security_frame = None
        self.set_multichannel_button = None
        self.clear_alarm_button = None
        self.interlock_indicator = None
        self.interlock_tooltip = None
        self.alarm_tooltip = None
        self.alarm_indicator = None
        self.multichannel_frame = None
        self.channel_frame = None
        self.main_frame = None
        self.root = parent_frame

        self.m = module  # Simulated module with 4 channels
        self.channel_names = channel_names
        for i in range(self.m.number_of_channels):
            if i not in self.channel_names:
                self.channel_names[i] = f"Channel {i}"  # default name for the channel
        self.command_queue = queue.Queue()
        self.device_lock = threading.Lock()

        self.alarm_detected = True # to avoid sending the alarm message when the GUI is started with the module alarm already active
        self.silence_alarm = silence

        self.create_gui()

    def create_gui(self):
        start_mainloop = False
        if self.root is None:
            self.root = tk.Tk()
            self.root.title("Caen HVPS GUI")
            start_mainloop = True

        self.main_frame = self.create_main_frame()
        self.alarm_frame = self.create_alarm_frame(self.main_frame)
        self.channel_frame = self.create_channels_frame(self.main_frame)
        if self.m.number_of_channels > 1:
            self.multichannel_frame = self.create_multichannel_frame(self.channel_frame)
        self.security_frame = self.create_security_frame(self.main_frame)

        self.start_background_threads()

        if start_mainloop:
            self.root.mainloop()

    def create_main_frame(self):
        main_frame = tk.LabelFrame(self.root, text=f"Module {self.m.name}", font=("", 16), bg="lightgray", padx=10, pady=10, labelanchor="n", bd=4)
        main_frame.pack(fill="both", expand=True)
        return main_frame

    def create_alarm_frame(self, frame):
        alarm_frame = tk.Frame(frame, bg="gray", padx=20, pady=20)
        alarm_frame.grid(row=1, column=0, padx=10, pady=10, sticky="N")

        tk.Label(
            alarm_frame, text="Module", font=("Arial", 14, "bold"), bg="gray"
        ).grid(row=0, column=0, columnspan=2)

        tk.Label(
            alarm_frame, text="Alarm", font=("Arial", 12, "bold"), bg="gray", fg="black"
        ).grid(row=1, column=0)
        intlck_label = tk.Label(
            alarm_frame,
            text="Interlock",
            font=("Arial", 12, "bold"),
            bg="gray",
            fg="black",
        )
        intlck_label.grid(row=1, column=1)
        ToolTip(intlck_label, f"Interlock mode: {self.m.interlock_mode}")

        self.alarm_indicator = tk.Canvas(
            alarm_frame, width=30, height=30, bg="red", highlightthickness=0
        )
        self.alarm_indicator.grid(row=2, column=0, padx=10, pady=10)
        self.alarm_tooltip = ToolTip(self.alarm_indicator, "Alarm signal")

        self.interlock_indicator = tk.Canvas(
            alarm_frame, width=30, height=30, bg="green", highlightthickness=0
        )
        self.interlock_indicator.grid(row=2, column=1, padx=10, pady=10)
        self.interlock_tooltip = ToolTip(self.interlock_indicator, "Interlock signal")

        self.clear_alarm_button = tk.Button(
            alarm_frame,
            text="Clear alarm signal",
            font=("Arial", 10),
            bg="navy",
            fg="white",
            command=lambda: self.issue_command(self.clear_alarm),
        )
        self.clear_alarm_button.grid(row=3, column=0, columnspan=2, pady=10)

        return alarm_frame

    def create_channels_frame(self, frame):
        channels_frame = tk.Frame(frame, bg="darkblue", padx=10, pady=10)
        channels_frame.grid(row=1, column=1, columnspan=2, rowspan=2, padx=10, pady=10)

        tk.Label(
            channels_frame,
            text="Channels",
            font=("Arial", 14, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=0, column=0, columnspan=7, pady=10)
        tk.Label(
            channels_frame,
            text="state",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=1)
        tk.Label(
            channels_frame,
            text="Turn on/off",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=2)
        tk.Label(
            channels_frame,
            text="Set vset (V)",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=3, columnspan=2)
        tk.Label(
            channels_frame,
            text="vset (V)",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=5)
        tk.Label(
            channels_frame,
            text="vmon (V)",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=6)
        tk.Label(
            channels_frame,
            text="imon (uA)",
            font=("Arial", 10, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=1, column=7)

        self.vset_entries = []
        self.vset_labels = []
        self.vmon_labels = []
        self.imon_labels = []
        self.state_indicators = []
        self.state_tooltips = []
        self.turn_buttons = []
        self.set_buttons = []
        for i in range(self.m.number_of_channels):
            channel_button = tk.Button(
                channels_frame,
                text=f"{self.channel_names[i]}",
                font=("Arial", 12, "bold"),
                bg="darkblue",
                fg="white",
                borderwidth=0,
                highlightthickness=0,
                command=lambda x=i: self.issue_command(
                    self.open_channel_property_window, x
                ),
            )
            channel_button.grid(row=i + 2, column=0, padx=10, pady=5)
            ToolTip(channel_button, f"Channel {i}: click for more setting options.")

            state_indicator = tk.Canvas(
                channels_frame, width=20, height=20, bg="black", highlightthickness=0
            )
            state_indicator.grid(row=i + 2, column=1, sticky="NSEW", padx=5, pady=5)
            self.state_indicators.append(state_indicator)
            self.state_tooltips.append(ToolTip(state_indicator, "State:"))

            turn_button = tk.Button(
                channels_frame,
                text="--------",
                font=("Arial", 9),
                bg="navy",
                fg="white",
                command=lambda x=i: self.issue_command(self.toggle_channel, x),
            )
            turn_button.grid(row=i + 2, column=2, padx=35, pady=5)
            self.turn_buttons.append(turn_button)

            set_button = tk.Button(
                channels_frame,
                text="Set",
                font=("Arial", 9),
                bg="navy",
                fg="white",
                command=lambda x=i: self.issue_command(self.set_vset, x),
            )
            set_button.grid(row=i + 2, column=3, sticky="NSW", padx=0, pady=5)
            self.set_buttons.append(set_button)

            vset_entry = tk.Entry(channels_frame, width=7, justify="center")
            vset_entry.insert(0, str(self.m.channels[i].vset))
            vset_entry.grid(row=i + 2, column=4, sticky="NSE", padx=0, pady=5)
            vset_entry.bind(
                "<Return>", lambda event, x=i: self.issue_command(self.set_vset, x)
            )
            self.vset_entries.append(vset_entry)

            vset_label = tk.Label(channels_frame, width=7, justify="center", text="-1")
            vset_label.grid(row=i + 2, column=5, sticky="NS", padx=10, pady=5)
            self.vset_labels.append(vset_label)

            vmon_label = tk.Label(channels_frame, width=7, justify="center", text="-1")
            vmon_label.grid(row=i + 2, column=6, sticky="NS", padx=10, pady=5)
            self.vmon_labels.append(vmon_label)

            imon_label = tk.Label(channels_frame, width=7, justify="center", text="-1")
            imon_label.grid(row=i + 2, column=7, sticky="NS", padx=10, pady=5)
            self.imon_labels.append(imon_label)

        return channels_frame

    def create_multichannel_frame(self, frame):
        checkbox_frame = tk.Frame(frame, bg="darkblue")
        checkbox_frame.grid(
            row=self.m.number_of_channels + 2, column=1, columnspan=6, pady=10
        )

        tk.Label(
            checkbox_frame,
            text="Multichannel control",
            font=("Arial", 12, "bold"),
            bg="darkblue",
            fg="white",
        ).grid(row=0, column=0, columnspan=2, pady=10)

        self.channel_vars = []
        for i in range(self.m.number_of_channels):
            var = tk.IntVar()
            self.channel_vars.append(var)
            tk.Checkbutton(
                checkbox_frame,
                text=f" {self.channel_names[i]}",
                variable=var,
                font=("Arial", 10),
                bg="darkblue",
                fg="white",
                selectcolor="gray",
                borderwidth=0,
                highlightthickness=0,
            ).grid(row=i + 1, column=0, sticky="w", padx=20)
            var.set(1)

        self.set_multichannel_button = tk.Button(
            checkbox_frame,
            text="Set multichannel",
            font=("Arial", 10),
            bg="navy",
            fg="white",
            command=lambda: self.issue_command(self.set_multichannel_vset_and_turn_on),
        )
        self.set_multichannel_button.grid(row=1, column=1, rowspan=4, padx=20, pady=5)
        return frame

    def create_security_frame(self, frame):
        security_frame = tk.Frame(frame)
        security_frame.grid(row=2, column=0, padx=10, pady=10, sticky="NWE")
        all_channels = {self.channel_names[i] : self.m.channels[i] for i in range(self.m.number_of_channels)}
        all_locks = tuple([self.device_lock])
        self.checksframe = ChecksFrame(security_frame, checks=self.checks, all_channels=all_channels, all_locks=all_locks)
        return security_frame

    def open_channel_property_window(self, channel_number):
        def values_from_description(description_: str | dict) -> list[str]:
            if isinstance(description_, str):
                # e.g.  'VAL:XXXX.X Set VSET value' -> [] ; 'VAL:RAMP/KILL Set POWER DOWN mode value' -> ['RAMP', 'KILL']
                # for hvps version <= 0.1.0
                valid_values = description_.split("VAL:")
                if len(valid_values) == 1:
                    return []
                valid_values = valid_values[1].split(" ")[0]
                if "/" not in valid_values:
                    return []
                return valid_values.split("/")
            elif isinstance(description_, dict):
                # e.g. {'command' : 'PDWN', 'input_type': str, 'allowed_input_values': ['RAMP', 'KILL'], 'output_type': None, 'possible_output_values': []}
                # e.g. {'command' : 'RUP', 'input_type': float, 'allowed_input_values': [], 'output_type': None, 'possible_output_values': []}
                # for hvps version >= 0.1.1
                return description_["allowed_input_values"]
            return []

        # Crear la nueva ventana
        new_window = tk.Toplevel(self.root)
        new_window.title(f"{self.channel_names[channel_number]}")
        new_window.configure(bg="darkblue")

        ch = self.m.channels[channel_number]
        try:
            set_properties = (
                hvps.commands.caen.channel._SET_CHANNEL_COMMANDS
            )  # version >= 0.1.1
        except AttributeError:
            set_properties = (
                hvps.commands.caen.channel._set_channel_commands
            )  # version <= 0.1.0
        properties = ch.__dir__()

        entries = {}
        for prop, description in set_properties.items():
            p = prop.lower()
            if p not in properties or callable(getattr(ch, p)) or p == "vset":
                continue

            label = tk.Label(
                new_window, text=p, font=("Arial", 12), bg="blue", fg="white"
            )
            label.grid(row=len(entries), column=0, padx=10, pady=5, sticky="e")
            ToolTip(
                label,
                description["description"]
                if isinstance(description, dict)
                else description,
            )  # hvps version < 0.1.1 is str, >= 0.1.1 is dict

            values = values_from_description(description)
            if values:
                selected_option = tk.StringVar(new_window)
                selected_option.set(getattr(ch, p))

                option_menu = tk.OptionMenu(new_window, selected_option, *values)
                option_menu.config(font=("Arial", 12))
                option_menu.grid(row=len(entries), column=1, padx=10, pady=5)
                entries[p] = option_menu

            else:
                entry = tk.Entry(
                    new_window, font=("Arial", 12), width=10, justify="center"
                )
                entry.grid(row=len(entries), column=1, padx=10, pady=5)
                entry.insert(0, str(getattr(ch, p)))
                entries[p] = entry

        # Botones "Cancel" y "Apply"
        cancel_button = tk.Button(
            new_window,
            text="Cancel",
            font=("Arial", 10),
            bg="navy",
            fg="white",
            command=new_window.destroy,
        )
        cancel_button.grid(row=len(properties), column=0, padx=10, pady=10, sticky="e")

        def apply_changes():
            print("Setting:")
            for p, entry in entries.items():
                if entry.winfo_class() == "Menubutton":
                    value = entry.cget("text")
                else:
                    value = entry.get()
                try:
                    value = float(value)
                except ValueError:
                    pass
                setattr(ch, p, value)
                print(f"  {p}\t-> {value}")
            new_window.destroy()
            print()

        apply_button = tk.Button(
            new_window,
            text="Apply",
            font=("Arial", 10),
            bg="darkblue",
            fg="white",
            command=lambda: self.issue_command(apply_changes),
        )
        apply_button.grid(row=len(properties), column=1, padx=10, pady=10, sticky="w")

    def start_background_threads(self):
        threading.Thread(target=self.read_loop, daemon=True).start()
        threading.Thread(target=self.process_commands, daemon=True).start()

    def process_commands(self):
        while True:
            func, args, kwargs = self.command_queue.get()
            with self.device_lock:
                func(*args, **kwargs)
            self.command_queue.task_done()
            if self.root.cget("cursor") == "watch" and func.__name__ != "read_values":
                self.root.config(cursor="")

    def issue_command(self, func, *args, **kwargs):
        # do not stack read_values commands (critical if reading values is slow)
        if (
            func.__name__ == "read_values"
            and (func, args, kwargs) in self.command_queue.queue
        ):
            return
        # print('\n'), [print(i) for i in self.command_queue.queue] # debug
        self.command_queue.put((func, args, kwargs))
        if (
            func.__name__ != "read_values"
        ):  # because it is constantly reading values in the background
            self.root.config(cursor="watch")
            self.root.update()

    def set_vset(self, channel_number, check=True):
        prev_vset = float(self.vset_labels[channel_number].cget("text"))
        try:
            vset_value = float(self.vset_entries[channel_number].get())
        except ValueError:
            self.vset_entries[channel_number].delete(0, tk.END)
            self.vset_entries[channel_number].insert(
                0, str(self.m.channels[channel_number].vset)
            )
            print("ValueError: Set voltage value must be a number")
            return False
        self.m.channels[channel_number].vset = vset_value
        if check and self.checksframe is not None:
            if not self.checksframe.check_conditions(): # TODO: better use simulate_check_conditions ??
                self.m.channels[channel_number].vset = prev_vset
                self.vset_entries[channel_number].config(fg="red")
                return False
            else:
                self.vset_entries[channel_number].config(fg="black")
        return True

    def set_multichannel_vset_and_turn_on(self, check=True):
        prev_vsets = [float(label.cget("text")) for label in self.vset_labels]
        for i, entry in enumerate(self.vset_entries):
            if self.channel_vars[i].get():
                self.set_vset(i, check=False) # do check after all the vset values are set
                entry.delete(0, tk.END)
                entry.insert(0, str(self.m.channels[i].vset))
        if check and self.checksframe is not None:
            if not self.checksframe.check_conditions(): # TODO: better use simulate_check_conditions ??
                for i, ch in enumerate(self.m.channels):
                    if self.channel_vars[i].get():
                        ch.vset = prev_vsets[i]
                return False
        # turn on if all the checks passed
        for i, chvar in enumerate(self.channel_vars):
            if chvar.get():
                self.m.channels[i].turn_on()
        return True

    def clear_alarm(self):
        self.m.clear_alarm_signal()
        self.alarm_detected = False

    def toggle_channel(self, channel_number):
        ch = self.m.channels[channel_number]
        if ch.stat["ON"]:
            ch.turn_off()
        else:
            self.set_vset(channel_number)
            ch.turn_on()

    def set_vset_and_turn_on(self, channel_number):
        entry = self.vset_entries[channel_number]
        self.m.channels[channel_number].vset = float(entry.get())
        self.m.channels[channel_number].turn_on()
        entry.delete(0, tk.END)
        entry.insert(0, str(self.m.channels[channel_number].vset))

    def read_loop(self):
        while True:
            self.issue_command(self.read_values)
            time.sleep(1)

    def read_values(self):
        for i, ch in enumerate(self.m.channels):
            self.vset_labels[i].config(text=f"{ch.vset:.1f}")
            self.vmon_labels[i].config(text=f"{ch.vmon:.1f}")
            self.imon_labels[i].config(text=f"{ch.imon:.3f}")
            self.update_state_indicator(i, ch)
        self.update_alarm_indicators()

    def update_state_indicator(self, channel_number, channel):
        # Update the state indicator
        stat = channel.stat.copy()
        if stat["TRIP"]:
            state_indicator_color = "red"
            state_tooltip_text = "TRIP"
        elif stat["DIS"]:
            state_indicator_color = "black"
            state_tooltip_text = "DISABLED"
        elif stat["KILL"]:
            state_indicator_color = "orange"
            state_tooltip_text = "KILL"
        elif stat["ILK"]:
            state_indicator_color = "yellow"
            state_tooltip_text = "INTERLOCK"
        else:
            if stat["ON"]:
                state_indicator_color = "green2"
                state_tooltip_text = "ON"
            else:
                state_indicator_color = "dark green"
                state_tooltip_text = "OFF"
            if stat["RUP"]:
                state_tooltip_text += " (RAMP UP)"
            if stat["RDW"]:
                state_tooltip_text += " (RAMP DOWN)"
        self.state_indicators[channel_number].configure(bg=state_indicator_color)
        self.state_tooltips[channel_number].change_text(f"State: {state_tooltip_text}")

        self.turn_buttons[channel_number].configure(
            text="TURN OFF" if stat["ON"] else "TURN  ON"
        )

    def update_alarm_indicators(self):
        bas = self.m.board_alarm_status.copy()
        ilk = self.m.interlock_status
        self.alarm_indicator.config(
            bg="red"
            if any([v for k, v in bas.items()])
            else "green"
        )
        self.alarm_tooltip.change_text(
            f"Alarm signal: {[k for k, v in bas.items() if v]}"
        )
        self.interlock_indicator.config(
            bg="red" if ilk else "green"
        )
        self.interlock_tooltip.change_text(
            f"Interlock signal: {ilk}"
        )

        if any([v for k, v in bas.items()]):
            if not self.alarm_detected:
                self.alarm_detected = True
                self.action_when_alarm()
        else:
            self.alarm_detected = False
    
    def action_when_alarm(self, board_alarm_status = None):
        if board_alarm_status is None:
            board_alarm_status = self.m.board_alarm_status.copy()
        message = f"Alarm detected in module {self.m.name}:\n"
        for k, v in board_alarm_status.items():
            if v:
                message += f"  {k}"
                if 'CH' in k:
                    message += f" ({self.channel_names[int(k[-1])]})"
        print(message)
        if not self.silence_alarm:
            send_slack_message(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Enable test mode")
    parser.add_argument("--port", type=str, help="Select port", default="/dev/ttyUSB0")
    parser.add_argument("--silence", action="store_true", help="Silence alarm")

    args = parser.parse_args()
    CHECKS = [
        Check(
            name="1bar, Vgem",
            channels={},
            condition="gem top.vset - gem bottom.vset <= 270",
            description="Maximum Vgem = 270 V",
        ),

        Check(
            name="1bar, Vmesh",
            channels={},
            condition="mesh left.vset <= 300",
            description="Maximum Vmesh = 300 V",
        ),
    ]

    if not args.test:
        with hvps.Caen(port=args.port) as caen:
            print("port:", caen.port)
            print("baudrate:", caen.baudrate)
            m = caen.module(0)
            CaenHVPSGUI(module=m, channel_names=CHANNEL_NAMES, silence=args.silence, checks=CHECKS)

    else:
        from simulators import *  # noqa: F403

        m = ModuleSimulator(4)  # noqa: F405
        CaenHVPSGUI(module=m, channel_names=CHANNEL_NAMES, silence=args.silence, checks=CHECKS)
