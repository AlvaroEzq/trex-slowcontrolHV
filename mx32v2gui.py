from __future__ import annotations

import tkinter as tk
import argparse

from mx32v2 import MX32v2, SENSORS, SENSOR_VALUE_NAMES, failed_sensor_reading
from channel import ChannelState
from check import Check
from checkframe import ChecksFrame
from utilsgui import ToolTip
from devicegui import DeviceGUI

# Consecutive failed reads that a sensor (or the controller) is allowed before the
# failure is reported. A single Modbus timeout every few hours is normal and solves
# itself, and at the default read_loop_time this still reports a real outage in a
# few seconds. Configurable at run time from the advanced options menu.
DEFAULT_READ_FAILURES_TO_WARN = 3

COLOR_OK = "green"
COLOR_ALARM = "red"
COLOR_FAULT = "dark orange"
COLOR_UNKNOWN = "orange"
COLOR_IDLE = "grey"

# Status flags that are not alarms but still have to be visible: a sensor in
# fault or out of range is not measuring, so its "no alarm" means nothing.
STATUS_FLAGS = {
    "fault": "FAULT",
    "out_of_range": "OUT OF RANGE",
    "under_range": "UNDER RANGE",
    "over_range": "OVER RANGE",
    "maintenance": "MAINTENANCE",
}


class MX32v2GUI(DeviceGUI):
    """
    A GUI class for monitoring the gas sensors connected to an MX32v2 controller.

    Inherits from DeviceGUI and provides specific functionality for the MX32v2.
    """

    def __init__(self, device, parent_frame=None, sensors=None, log=True, auto_gui_update=True):
        if sensors is None:
            sensors = SENSORS
        self.sensors = tuple(sensors)
        self.sensors_by_name = {sensor.name: sensor for sensor in self.sensors}

        self.value_labels = {}
        self.alarm_labels = {}
        self.status_labels = {}
        # consecutive failed reads, per sensor name (None: the controller itself)
        self.read_failures = {}

        channels_states = {}
        for sensor in self.sensors:
            channels_states[sensor.name] = ChannelState(
                sensor.name,
                list(SENSOR_VALUE_NAMES),
                # every flag gets a threshold of 1 so that any change of state is
                # logged (booleans compare as 0/1), and the concentration gets the
                # threshold configured for the sensor
                thresholds={
                    **{name: 1 for name in SENSOR_VALUE_NAMES},
                    "concentration": sensor.log_threshold,
                },
                precisions={"concentration": 2},
                units={"concentration": sensor.unit},
            )

        super().__init__(
                        device=device,
                        channels_states=channels_states,
                        parent_frame=parent_frame,
                        auto_gui_update=auto_gui_update,
                        logging_enabled=log,
                        read_loop_time=2,
                        )

    def create_gui(self):
        # create_gui() is called by DeviceGUI.__init__ after config_params is built
        # and before the read loop starts, so this is where an extra parameter can
        # join the ones offered by the advanced options menu.
        self.config_params.setdefault("read_failures_to_warn", DEFAULT_READ_FAILURES_TO_WARN)

        self.main_frame = tk.LabelFrame(self.frame, text=f"{self.device.name}", font=("", 16),
                                        padx=10, pady=10, labelanchor="n", bd=4)
        self.main_frame.pack(fill="both", expand=True)

        for column, sensor in enumerate(self.sensors):
            self.create_sensor_frame(self.main_frame, sensor).grid(row=0, column=column,
                                                                  padx=5, pady=5, sticky="nsew")

    def create_sensor_frame(self, frame, sensor):
        sensor_frame = tk.LabelFrame(frame, text=f"{sensor.name} (line {sensor.line})")

        # row 0: the measurement
        value_label = tk.Label(sensor_frame, text="NO DATA", fg=COLOR_UNKNOWN, font=("", 14))
        value_label.grid(row=0, column=0, columnspan=len(sensor.alarms) or 1, padx=5, pady=5)
        self.value_labels[sensor.name] = value_label

        # row 1: one indicator per configured alarm
        alarm_labels = []
        for column, alarm in enumerate(sensor.alarms):
            label = tk.Label(sensor_frame, text=f"{alarm} {alarm.level:g} {sensor.unit}",
                             fg=COLOR_IDLE, relief="ridge", width=10)
            label.grid(row=1, column=column, padx=2, pady=2)
            ToolTip(label, f"Alarm {alarm.number} of {sensor.name}, configured at"
                           f" {alarm.level:g} {sensor.unit}")
            alarm_labels.append(label)
        self.alarm_labels[sensor.name] = alarm_labels

        # row 2: fault / range / maintenance flags
        status_label = tk.Label(sensor_frame, text="no communication", fg=COLOR_UNKNOWN)
        status_label.grid(row=2, column=0, columnspan=len(sensor.alarms) or 1, padx=5, pady=5)
        self.status_labels[sensor.name] = status_label

        return sensor_frame

    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel states here. Widgets are updated by update_gui(), on the main thread.
        try:
            self.device.open()
        except Exception as e:
            if self.handle_read_failure(None, f"Could not connect to {self.device.name}: {e}"):
                # the controller has been unreachable long enough to be a real
                # outage: the values on screen are meaningless, mark them as unknown
                for sensor in self.sensors:
                    self.channels_state[sensor.name].set_state(failed_sensor_reading())
            return
        self.handle_read_recovery(None, f"{self.device.name} is answering again")

        try:
            for sensor in self.sensors:
                try:
                    values = self.device.read_sensor(sensor)
                except Exception as e:
                    if not self.handle_read_failure(
                        sensor.name, f"Could not read sensor '{sensor.name}': {e}"
                    ):
                        continue # probably a blip: keep the values read last time
                    values = failed_sensor_reading()
                else:
                    self.handle_read_recovery(
                        sensor.name, f"Sensor '{sensor.name}' is answering again"
                    )
                previous_values = self.channels_state[sensor.name].get_values()
                self.channels_state[sensor.name].set_state(values)
                self.log_alarm_transitions(sensor, previous_values, values)
        finally:
            self.device.close()

    def read_failures_to_warn(self):
        return max(1, int(self.config_params.get("read_failures_to_warn",
                                                 DEFAULT_READ_FAILURES_TO_WARN)))

    def handle_read_failure(self, key, message):
        """
        Count a failed read and report it only once it has persisted.

        A single Modbus timeout every few hours is normal and solves itself, so the
        first failures are only recorded at debug level, where they do not reach the
        Slack/Mattermost handlers. Once the same sensor (or the controller) has
        failed 'read_failures_to_warn' reads in a row the problem is real and gets
        logged as a warning, once, until it recovers.

        Returns True when the failure has lasted long enough to be published as a
        failed reading; while it returns False the caller keeps the last values.
        """
        failures = self.read_failures.get(key, 0) + 1
        self.read_failures[key] = failures
        to_warn = self.read_failures_to_warn()

        if failures < to_warn:
            self.logger.debug(f"{message} (failure {failures} of {to_warn}, tolerated)")
            return False
        if failures == to_warn:
            self.logger.warning(f"{message} (failed {failures} reads in a row)")
        else:
            self.logger.debug(message) # already warned about this one
        return True

    def handle_read_recovery(self, key, message):
        """Report a sensor (or the controller) that reads again, if it was warned about."""
        failures = self.read_failures.pop(key, 0)
        if failures >= self.read_failures_to_warn():
            self.logger.info(f"{message} after {failures} failed reads")
        elif failures:
            self.logger.debug(f"{message} after {failures} failed reads")

    def log_alarm_transitions(self, sensor, previous_values, values):
        """
        Log every alarm that has just been raised (critical) or cleared (info).

        Only the transitions are logged: the read loop runs every few seconds and
        the critical records are forwarded to Slack/Mattermost, so logging on every
        read while an alarm is standing would flood those channels.
        """
        if not values.get("comm_ok", False):
            # the flags of a failed reading are all False, which is not a real
            # "alarm cleared". Alarms that are still standing get logged again once
            # the communication comes back, which is what we want after going blind.
            return

        concentration = values.get("concentration", -1.0)
        for alarm in sensor.alarms:
            active = values.get(alarm.key, False)
            if active == previous_values.get(alarm.key, False):
                continue
            if active:
                self.logger.critical(
                    f"{self.device.name} {sensor.name} (line {sensor.line}): GAS ALARM"
                    f" {alarm.number} ACTIVATED at {concentration:.2f} {sensor.unit}"
                    f" (threshold {alarm.level:g} {sensor.unit})"
                )
            else:
                self.logger.info(
                    f"{self.device.name} {sensor.name} (line {sensor.line}): gas alarm"
                    f" {alarm.number} cleared at {concentration:.2f} {sensor.unit}"
                    f" (threshold {alarm.level:g} {sensor.unit})"
                )

    def update_gui(self):
        for sensor in self.sensors:
            values = self.channels_state[sensor.name].get_values()
            self.update_sensor_widgets(sensor, values)

    def update_sensor_widgets(self, sensor, values):
        alarms_active = [values.get(alarm.key, False) for alarm in sensor.alarms]
        flags_active = [text for key, text in STATUS_FLAGS.items() if values.get(key, False)]

        if not values.get("comm_ok", False):
            # nothing was read, so neither the measurement nor the flags mean anything
            self.value_labels[sensor.name].config(text="NO DATA", fg=COLOR_UNKNOWN)
            for label in self.alarm_labels[sensor.name]:
                label.config(fg=COLOR_IDLE)
            self.status_labels[sensor.name].config(text="no communication", fg=COLOR_UNKNOWN)
            return

        concentration = values.get("concentration", -1.0)
        self.value_labels[sensor.name].config(
            text=f"{concentration:.2f} {sensor.unit}",
            fg=COLOR_ALARM if any(alarms_active) else (COLOR_FAULT if flags_active else COLOR_OK),
        )
        for label, active in zip(self.alarm_labels[sensor.name], alarms_active):
            label.config(fg=COLOR_ALARM if active else COLOR_IDLE)
        self.status_labels[sensor.name].config(
            text=", ".join(flags_active) if flags_active else "OK",
            fg=COLOR_FAULT if flags_active else COLOR_OK,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MX32v2 GUI Monitor")
    parser.add_argument("--port", type=str, default="/dev/ttyUSB1", help="Serial port of the MX32v2 (e.g. /dev/ttyUSB0)")
    parser.add_argument("--baudrate", type=int, default=9600, help="Modbus baudrate (default: 9600)")
    parser.add_argument("--slave-id", type=int, default=0, help="Modbus slave number (default: 0)")
    parser.add_argument("--test", action="store_true", help="Use a simulated device for testing")
    args = parser.parse_args()

    if args.test:
        from simulators import MX32v2Simulator
        print("Using MX32v2 Simulator")
        mx32_device = MX32v2Simulator()
    else:
        if args.port is None:
            print("Please provide a serial port using --port")
            exit(1)
        mx32_device = MX32v2(port=args.port, baudrate=args.baudrate, slave_id=args.slave_id)

    MX32v2GUI(device=mx32_device)
