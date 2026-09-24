from __future__ import annotations

import argparse
import math
import tkinter as tk

from trexdmsc.devices.bronkhorst import Bronkhorst, BRONKHORSTS, GAS_PANEL_HOST
from trexdmsc.core.channel import ChannelState
from trexdmsc.gui.base.widgets import ToolTip
from trexdmsc.gui.base.devicegui import DeviceGUI
from trexdmsc.gui.base.readfailures import ReadFailureMixin
from trexdmsc.gui.base.readonly import write_command

# Consecutive reads the measurement has to stay above setpoint + margin before the
# alarm is raised: right after lowering the setpoint the measurement is above the new
# one for a while, which is not an alarm. Configurable from the advanced options menu.
DEFAULT_SETPOINT_ALARM_READS = 5

COLOR_OK = "green"
COLOR_ALARM = "red"
COLOR_UNKNOWN = "orange"
COLOR_IDLE = "grey"

ALARM_MAX = "max"
ALARM_SETPOINT = "setpoint"


def failed_reading(controller=True):
    """Placeholder values for an instrument that cannot be read."""
    values = {"measure": math.nan, "comm_ok": False}
    if controller:
        values["setpoint"] = math.nan
    return values


class BronkhorstGUI(ReadFailureMixin, DeviceGUI):
    """
    A GUI class for one Bronkhorst of the gas panel: a pressure/flow controller
    (measurement and setpoint) or a flow meter (measurement only).

    Alarms, logged as critical when raised (so they reach Slack/Mattermost):
    - the measurement goes above config.max_alarm.
    - the measurement stays above the setpoint + config.setpoint_margin_alarm.
    """

    def __init__(self, device, parent_frame=None, log=True, auto_gui_update=True, read_only=False):
        self.config = device.config
        self.read_only = read_only
        self.alarms = {}
        if self.config.max_alarm is not None:
            self.alarms[ALARM_MAX] = False
        if self.config.controller and self.config.setpoint_margin_alarm is not None:
            self.alarms[ALARM_SETPOINT] = False
        self.reads_above_setpoint = 0

        self.alarm_labels = {}
        self.setpoint_entry = None
        self.setpoint_button = None

        value_names = ["measure", "setpoint", "comm_ok"] if self.config.controller else ["measure", "comm_ok"]
        channel_state = ChannelState(
            self.config.name,
            value_names,
            thresholds={
                "measure": self.config.log_threshold,
                # one ProPar count: log every setpoint change
                "setpoint": self.config.full_scale / 32000,
                "comm_ok": 1,
            },
            precisions={"measure": self.config.precision, "setpoint": self.config.precision},
            units={"measure": self.config.unit, "setpoint": self.config.unit},
        )

        super().__init__(
                        device=device,
                        channels_states={self.config.name: channel_state},
                        parent_frame=parent_frame,
                        auto_gui_update=auto_gui_update,
                        logging_enabled=log,
                        read_loop_time=1,
                        )

    @property
    def channel_state(self):
        return self.channels_state[self.config.name]

    # ------------------------------------------------------------------ GUI layout
    def create_gui(self):
        self.add_read_failures_config_param()
        self.config_params.setdefault("setpoint_alarm_reads", DEFAULT_SETPOINT_ALARM_READS)

        title = f"{self.config.name}: {self.config.description}"
        if self.read_only:
            title += " (read-only)"
        self.main_frame = tk.LabelFrame(self.frame, text=title, font=("", 12),
                                        padx=10, pady=5, labelanchor="n", bd=3)
        self.main_frame.pack(fill="both", expand=True)

        # row 0: the measurement
        tk.Label(self.main_frame, text=f"{self.config.measure_tag} [{self.config.unit}]:",
                 width=16, anchor="e").grid(row=0, column=0, sticky="e")
        self.measure_label = tk.Label(self.main_frame, text="NO DATA", fg=COLOR_UNKNOWN,
                                      font=("", 14), width=9)
        self.measure_label.grid(row=0, column=1, padx=5)

        # row 1: the setpoint (controllers only)
        if self.config.controller:
            tk.Label(self.main_frame, text=f"{self.config.setpoint_tag} set [{self.config.unit}]:",
                     width=16, anchor="e").grid(row=1, column=0, sticky="e")
            self.setpoint_label = tk.Label(self.main_frame, text="----", width=9)
            self.setpoint_label.grid(row=1, column=1, padx=5)

            self.setpoint_entry = tk.Entry(self.main_frame, width=7, justify="right",
                                           validate="key", validatecommand=self.validate_numeric_input)
            self.setpoint_entry.grid(row=1, column=2, padx=2)
            self.setpoint_entry.bind("<Return>", lambda event: self.request_setpoint())
            self.setpoint_button = tk.Button(self.main_frame, text="SET", width=3,
                                             command=self.request_setpoint)
            self.setpoint_button.grid(row=1, column=3, padx=2)
            ToolTip(self.setpoint_entry, f"New setpoint, from {self.config.setpoint_min:g}"
                                         f" to {self.config.max_setpoint:g} {self.config.unit}")
            if self.read_only:
                self.setpoint_entry.config(state="disabled")
                self.setpoint_button.config(state="disabled")

        # row 2: alarm indicators and communication status
        alarms_frame = tk.Frame(self.main_frame)
        alarms_frame.grid(row=2, column=0, columnspan=4, pady=(5, 0))
        if ALARM_MAX in self.alarms:
            label = tk.Label(alarms_frame, text=f"> {self.config.max_alarm:g} {self.config.unit}",
                             fg=COLOR_IDLE, relief="ridge", width=14)
            label.pack(side="left", padx=2)
            ToolTip(label, f"Alarm when {self.config.measure_tag} goes above"
                           f" {self.config.max_alarm:g} {self.config.unit}")
            self.alarm_labels[ALARM_MAX] = label
        if ALARM_SETPOINT in self.alarms:
            label = tk.Label(alarms_frame, text=f"> set + {self.config.setpoint_margin_alarm:g}",
                             fg=COLOR_IDLE, relief="ridge", width=14)
            label.pack(side="left", padx=2)
            ToolTip(label, f"Alarm when {self.config.measure_tag} stays above the setpoint"
                           f" by more than {self.config.setpoint_margin_alarm:g} {self.config.unit}")
            self.alarm_labels[ALARM_SETPOINT] = label
        self.status_label = tk.Label(alarms_frame, text="no communication", fg=COLOR_UNKNOWN)
        self.status_label.pack(side="left", padx=5)

    # ------------------------------------------------------------ hardware (thread)
    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel state here. Widgets are updated by update_gui(), on the main thread.
        try:
            values = self.device.read()
        except Exception as e:
            if self.handle_read_failure(None, f"Could not read {self.config.name}: {e}"):
                self.channel_state.set_state(failed_reading(self.config.controller))
            return # while tolerated, keep the values read last time
        self.handle_read_recovery(None, f"{self.config.name} is answering again")

        values["comm_ok"] = True
        self.channel_state.set_state(values)
        self.check_alarms(values)

    def check_alarms(self, values):
        measure = values["measure"]
        unit = self.config.unit
        tag = f"{self.config.name} {self.config.measure_tag}"

        if ALARM_MAX in self.alarms:
            active = measure > self.config.max_alarm
            self.log_alarm_transition(
                self.alarms[ALARM_MAX], active,
                f"{tag}: ALARM, {measure:.{self.config.precision}f} {unit} above the maximum"
                f" of {self.config.max_alarm:g} {unit}",
                f"{tag}: back below the maximum of {self.config.max_alarm:g} {unit}"
                f" ({measure:.{self.config.precision}f} {unit})",
            )
            self.alarms[ALARM_MAX] = active

        if ALARM_SETPOINT in self.alarms:
            setpoint = values["setpoint"]
            limit = setpoint + self.config.setpoint_margin_alarm
            self.reads_above_setpoint = self.reads_above_setpoint + 1 if measure > limit else 0
            reads_needed = max(1, int(self.config_params.get("setpoint_alarm_reads",
                                                             DEFAULT_SETPOINT_ALARM_READS)))
            # raised once it has persisted, cleared as soon as it is back
            active = (self.reads_above_setpoint >= reads_needed
                      or (self.alarms[ALARM_SETPOINT] and measure > limit))
            self.log_alarm_transition(
                self.alarms[ALARM_SETPOINT], active,
                f"{tag}: ALARM, {measure:.{self.config.precision}f} {unit} above the setpoint"
                f" of {setpoint:.{self.config.precision}f} {unit} by more than"
                f" {self.config.setpoint_margin_alarm:g} {unit}",
                f"{tag}: back within {self.config.setpoint_margin_alarm:g} {unit} of the"
                f" setpoint ({measure:.{self.config.precision}f} {unit}, setpoint"
                f" {setpoint:.{self.config.precision}f} {unit})",
            )
            self.alarms[ALARM_SETPOINT] = active

    @write_command
    def set_setpoint(self, value):
        self.device.set_setpoint(value)
        self.logger.info(f"{self.config.name}: setpoint set to {value:g} {self.config.unit}")

    # ------------------------------------------------------------- GUI (Tk thread)
    def request_setpoint(self):
        """Validate the setpoint entry and queue the command that writes it."""
        if self.read_only:
            return
        text = self.setpoint_entry.get()
        try:
            value = float(text)
        except ValueError:
            self.setpoint_entry.config(fg=COLOR_ALARM)
            self.logger.warning(f"{self.config.name}: setpoint '{text}' is not a number")
            return
        if not self.config.setpoint_min <= value <= self.config.max_setpoint:
            self.setpoint_entry.config(fg=COLOR_ALARM)
            self.logger.warning(f"{self.config.name}: setpoint {value:g} {self.config.unit} out of"
                                f" [{self.config.setpoint_min:g}, {self.config.max_setpoint:g}]")
            return
        self.setpoint_entry.config(fg="black")
        self.issue_command(self.set_setpoint, value)

    def is_focused(self, widget):
        try:
            return self.root.focus_get() is widget
        except (KeyError, tk.TclError): # focus on a widget Tk cannot resolve (e.g. a menu)
            return False

    def update_gui(self):
        values = self.channel_state.get_values()
        precision = self.config.precision

        if not values.get("comm_ok", False):
            self.measure_label.config(text="NO DATA", fg=COLOR_UNKNOWN)
            if self.config.controller:
                self.setpoint_label.config(text="----")
            for label in self.alarm_labels.values():
                label.config(fg=COLOR_IDLE)
            self.status_label.config(text="no communication", fg=COLOR_UNKNOWN)
            return

        any_alarm = any(self.alarms.values())
        self.measure_label.config(text=f"{values['measure']:.{precision}f}",
                                  fg=COLOR_ALARM if any_alarm else COLOR_OK)
        if self.config.controller:
            setpoint = values["setpoint"]
            self.setpoint_label.config(text=f"{setpoint:.{precision}f}")
            # show the current setpoint in the (still empty) entry once it is known
            if not self.read_only and not self.setpoint_entry.get() \
                    and not self.is_focused(self.setpoint_entry):
                self.setpoint_entry.insert(0, f"{setpoint:.{precision}f}")
        for key, label in self.alarm_labels.items():
            label.config(fg=COLOR_ALARM if self.alarms[key] else COLOR_IDLE)
        self.status_label.config(text="ALARM" if any_alarm else "OK",
                                 fg=COLOR_ALARM if any_alarm else COLOR_OK)


def main():
    configs = {config.name.split()[-1]: config for config in BRONKHORSTS} # P, Q, M
    parser = argparse.ArgumentParser(description="Bronkhorst GUI")
    parser.add_argument("--device", choices=sorted(configs), default="P",
                        help="Which Bronkhorst of the gas panel (default: P)")
    parser.add_argument("--host", type=str, default=GAS_PANEL_HOST,
                        help=f"Host of the bridge servers (default: {GAS_PANEL_HOST})")
    parser.add_argument("--port", type=int, default=None,
                        help="TCP port of the bridge server (default: the one of the device)")
    parser.add_argument("--read-only", action="store_true", help="Do not allow setpoint changes")
    parser.add_argument("--test", action="store_true", help="Use a simulated device for testing")
    args = parser.parse_args()

    config = configs[args.device]
    if args.test:
        from trexdmsc.simulators import BronkhorstSimulator
        device = BronkhorstSimulator(config)
    else:
        device = Bronkhorst(config, host=args.host, port=args.port)

    BronkhorstGUI(device=device, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
