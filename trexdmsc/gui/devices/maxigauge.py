from __future__ import annotations

import argparse
import tkinter as tk

from trexdmsc.devices.maxigauge import (MaxiGauge, MaxiGaugeError, GAUGES, GAUGE_VALUE_NAMES,
                                        STATUS_NAMES, STATUS_OK, VACUUM_HOST, MAXIGAUGE_PORT,
                                        failed_gauge_reading)
from trexdmsc.core.channel import ChannelState
from trexdmsc.gui.base.widgets import ToolTip
from trexdmsc.gui.base.devicegui import DeviceGUI
from trexdmsc.gui.base.readfailures import ReadFailureMixin

COLOR_OK = "green"
COLOR_ALARM = "red"
COLOR_FAULT = "dark orange"
COLOR_UNKNOWN = "orange"
COLOR_IDLE = "grey"

STATUS_UNDERRANGE = 1
STATUS_OVERRANGE = 2
STATUS_NO_SENSOR = 5


class MaxiGaugeGUI(ReadFailureMixin, DeviceGUI):
    """
    A GUI class for monitoring the vacuum gauges connected to the MaxiGauge.

    A gauge with a max_alarm raises an alarm (logged as critical, so it reaches
    Slack/Mattermost) when its pressure goes above it, or when it is over range.
    """

    def __init__(self, device, parent_frame=None, gauges=None, log=True, auto_gui_update=True):
        self.gauges = tuple(GAUGES if gauges is None else gauges)
        self.alarms = {gauge.name: False for gauge in self.gauges if gauge.max_alarm is not None}

        self.pressure_labels = {}
        self.status_labels = {}
        self.alarm_labels = {}

        channels_states = {}
        for gauge in self.gauges:
            channels_states[gauge.name] = ChannelState(
                gauge.name,
                list(GAUGE_VALUE_NAMES),
                # the pressure spans orders of magnitude: log it on a relative change
                relative_thresholds={"pressure": gauge.log_fraction},
                thresholds={"status": 1, "comm_ok": 1},
                units={"pressure": gauge.unit},
            )

        super().__init__(
                        device=device,
                        channels_states=channels_states,
                        parent_frame=parent_frame,
                        auto_gui_update=auto_gui_update,
                        logging_enabled=log,
                        read_loop_time=2,
                        )

    # ------------------------------------------------------------------ GUI layout
    def create_gui(self):
        self.add_read_failures_config_param()

        self.main_frame = tk.LabelFrame(self.frame, text=f"{self.device.name}", font=("", 12),
                                        padx=10, pady=5, labelanchor="n", bd=3)
        self.main_frame.pack(fill="both", expand=True)

        for column, text in enumerate(("Ch", "Gauge", "Pressure", "Status", "Alarm")):
            tk.Label(self.main_frame, text=text, font=("", 10, "bold")).grid(row=0, column=column, padx=4)

        for row, gauge in enumerate(self.gauges, start=1):
            tk.Label(self.main_frame, text=str(gauge.channel)).grid(row=row, column=0)
            name = f"{gauge.tag} {gauge.name}" if gauge.tag else gauge.name
            tk.Label(self.main_frame, text=name, anchor="w").grid(row=row, column=1, sticky="w")

            pressure_label = tk.Label(self.main_frame, text="NO DATA", fg=COLOR_UNKNOWN, width=14)
            pressure_label.grid(row=row, column=2)
            self.pressure_labels[gauge.name] = pressure_label

            status_label = tk.Label(self.main_frame, text="--", fg=COLOR_UNKNOWN, width=18)
            status_label.grid(row=row, column=3)
            self.status_labels[gauge.name] = status_label

            if gauge.name in self.alarms:
                alarm_label = tk.Label(self.main_frame, text=f"> {gauge.max_alarm:g} {gauge.unit}",
                                       fg=COLOR_IDLE, relief="ridge", width=12)
                alarm_label.grid(row=row, column=4, padx=2, pady=1)
                ToolTip(alarm_label, f"Alarm when the pressure of {name} goes above"
                                     f" {gauge.max_alarm:g} {gauge.unit}")
                self.alarm_labels[gauge.name] = alarm_label

    # ------------------------------------------------------------ hardware (thread)
    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel states here. Widgets are updated by update_gui(), on the main thread.
        for gauge in self.gauges:
            try:
                values = self.device.read_gauge(gauge)
            except MaxiGaugeError as e:
                # the MaxiGauge answered, but not for this gauge
                if not self.handle_read_failure(gauge.name, f"Could not read {gauge.name}: {e}"):
                    continue # probably a blip: keep the values read last time
                values = failed_gauge_reading()
            except Exception as e:
                # no answer at all (bridge server or serial link): the other gauges
                # would fail the same way, so count it once, for the whole device
                if self.handle_read_failure(None, f"Could not read {self.device.name}: {e}"):
                    for g in self.gauges:
                        self.channels_state[g.name].set_state(failed_gauge_reading())
                return
            else:
                self.handle_read_recovery(None, f"{self.device.name} is answering again")
                self.handle_read_recovery(gauge.name, f"{gauge.name} is answering again")

            self.channels_state[gauge.name].set_state(values)
            self.check_alarm(gauge, values)

    def check_alarm(self, gauge, values):
        if gauge.name not in self.alarms or not values.get("comm_ok", False):
            return
        status = values["status"]
        pressure = values["pressure"]
        if status == STATUS_OK:
            active = pressure > gauge.max_alarm
        elif status == STATUS_OVERRANGE:
            active = True # above the range of the gauge, so above any vacuum alarm level
        elif status == STATUS_UNDERRANGE:
            active = False
        else:
            return # error / off / no sensor: the pressure is unknown, keep the alarm state
        name = f"{gauge.tag} {gauge.name}" if gauge.tag else gauge.name
        self.log_alarm_transition(
            self.alarms[gauge.name], active,
            f"{self.device.name} {name}: VACUUM ALARM, pressure {pressure:.3e} {gauge.unit}"
            f" ({STATUS_NAMES.get(status, status)}) above {gauge.max_alarm:g} {gauge.unit}",
            f"{self.device.name} {name}: vacuum alarm cleared, pressure {pressure:.3e}"
            f" {gauge.unit} ({STATUS_NAMES.get(status, status)})",
        )
        self.alarms[gauge.name] = active

    # ------------------------------------------------------------- GUI (Tk thread)
    def update_gui(self):
        for gauge in self.gauges:
            values = self.channels_state[gauge.name].get_values()
            self.update_gauge_widgets(gauge, values)

    def update_gauge_widgets(self, gauge, values):
        alarm = self.alarms.get(gauge.name, False)
        if gauge.name in self.alarm_labels:
            self.alarm_labels[gauge.name].config(fg=COLOR_ALARM if alarm else COLOR_IDLE)

        if not values.get("comm_ok", False):
            self.pressure_labels[gauge.name].config(text="NO DATA", fg=COLOR_UNKNOWN)
            self.status_labels[gauge.name].config(text="no communication", fg=COLOR_UNKNOWN)
            return

        status = values["status"]
        status_text = STATUS_NAMES.get(status, f"status {status}")
        if status == STATUS_NO_SENSOR:
            self.pressure_labels[gauge.name].config(text="----", fg=COLOR_IDLE)
            self.status_labels[gauge.name].config(text=status_text, fg=COLOR_IDLE)
            return

        if status == STATUS_OK:
            color = COLOR_ALARM if alarm else COLOR_OK
        else:
            color = COLOR_ALARM if alarm else COLOR_FAULT
        self.pressure_labels[gauge.name].config(text=f"{values['pressure']:.3e} {gauge.unit}", fg=color)
        self.status_labels[gauge.name].config(text=status_text,
                                              fg=COLOR_OK if status == STATUS_OK else COLOR_FAULT)


def main():
    parser = argparse.ArgumentParser(description="MaxiGauge GUI Monitor")
    parser.add_argument("--host", type=str, default=VACUUM_HOST,
                        help=f"Host of the MaxiGauge bridge server (default: {VACUUM_HOST})")
    parser.add_argument("--port", type=int, default=MAXIGAUGE_PORT,
                        help=f"TCP port of the MaxiGauge bridge server (default: {MAXIGAUGE_PORT})")
    parser.add_argument("--test", action="store_true", help="Use a simulated device for testing")
    args = parser.parse_args()

    if args.test:
        from trexdmsc.simulators import MaxiGaugeSimulator
        device = MaxiGaugeSimulator()
    else:
        device = MaxiGauge(host=args.host, port=args.port)

    MaxiGaugeGUI(device=device, log=not args.test)


if __name__ == "__main__":
    main()
