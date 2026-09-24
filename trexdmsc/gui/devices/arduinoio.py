from __future__ import annotations

import argparse
import math
import time
import tkinter as tk

from trexdmsc.devices.arduinoio import ArduinoIO, ArduinoIOError, ARDUINOS, WATCHDOG_TIMEOUT
from trexdmsc.core.channel import ChannelState
from trexdmsc.gui.base.widgets import ToolTip
from trexdmsc.gui.base.devicegui import DeviceGUI
from trexdmsc.gui.base.readfailures import ReadFailureMixin
from trexdmsc.gui.base.readonly import write_command

# Read loop period (s). Every read cycle talks to the Arduino, which keeps its
# watchdog (WATCHDOG_TIMEOUT) from driving the outputs LOW, so it must stay well below.
READ_LOOP_TIME = 0.5
# A read cycle longer than this leaves too little margin to the watchdog: warn.
SLOW_CYCLE_TIME = 0.8 * WATCHDOG_TIMEOUT

COLOR_OK = "green"
COLOR_ALARM = "red"
COLOR_UNKNOWN = "orange"
COLOR_IDLE = "grey"
COLOR_ON = "green"
COLOR_OFF = "black"

LOW = "low"
HIGH = "high"


def failed_channel_reading():
    return {"value": math.nan, "comm_ok": False}


def failed_output_reading():
    return {"on": None, "comm_ok": False}


class ArduinoIOGUI(ReadFailureMixin, DeviceGUI):
    """
    A GUI class for an Arduino of the slow control with the trexdm_serial firmware:
    its analog sensors (with their alarms) and its relays (with their ON/OFF buttons).
    What is connected to the Arduino comes from its ArduinoIOConfig (device.config).

    The outputs are read on every read cycle, which is also what keeps the watchdog of
    the firmware from switching them off: the Arduino must be read every
    READ_LOOP_TIME seconds, also in read-only mode. The analog sensors can be read
    less often with the 'analog_read_every' parameter (advanced options menu) if a
    cycle takes too long.
    """

    def __init__(self, device, parent_frame=None, log=True, auto_gui_update=True, read_only=False):
        self.config = device.config
        self.read_only = read_only
        self.analog_channels = tuple(self.config.analog_channels)
        self.outputs = tuple(self.config.outputs)

        self.alarms = {}
        for channel in self.analog_channels:
            self.alarms[channel.name] = {}
            if channel.low_alarm is not None:
                self.alarms[channel.name][LOW] = False
            if channel.high_alarm is not None:
                self.alarms[channel.name][HIGH] = False

        self.cycle = 0
        # last state commanded to each output, until the next read confirms it
        self.commanded_outputs = {}
        self.slow_cycle_warned = False

        self.value_labels = {}
        self.indicator_labels = {}
        self.alarm_labels = {}
        self.output_labels = {}
        self.output_buttons = []

        channels_states = {}
        for channel in self.analog_channels:
            channels_states[channel.name] = ChannelState(
                channel.name,
                ["value", "comm_ok"],
                thresholds={"value": channel.log_threshold, "comm_ok": 1},
                precisions={"value": channel.precision},
                units={"value": channel.unit},
            )
        for output in self.outputs:
            channels_states[output.name] = ChannelState(
                output.name,
                ["on", "comm_ok"],
                thresholds={"on": 1, "comm_ok": 1},
            )

        super().__init__(
                        device=device,
                        channels_states=channels_states,
                        parent_frame=parent_frame,
                        auto_gui_update=auto_gui_update,
                        logging_enabled=log,
                        read_loop_time=READ_LOOP_TIME,
                        )

    # ------------------------------------------------------------------ GUI layout
    def create_gui(self):
        self.add_read_failures_config_param()
        self.config_params.setdefault("analog_read_every", 1)

        title = self.device.name + (" (read-only)" if self.read_only else "")
        self.main_frame = tk.LabelFrame(self.frame, text=title, font=("", 12),
                                        padx=10, pady=5, labelanchor="n", bd=3)
        self.main_frame.pack(fill="both", expand=True)

        if self.analog_channels:
            self.create_sensors_frame(self.main_frame).pack(fill="x", pady=(0, 5))
        if self.outputs:
            self.create_outputs_frame(self.main_frame).pack(fill="x")

    def create_sensors_frame(self, frame):
        sensors_frame = tk.LabelFrame(frame, text="Sensors")
        for row, channel in enumerate(self.analog_channels):
            name_label = tk.Label(sensors_frame, text=f"{channel.name} [{channel.unit}]:", anchor="e", width=12)
            name_label.grid(row=row, column=0, sticky="e")
            ToolTip(name_label, f"{channel.description} (Arduino sensor {channel.input})")

            value_label = tk.Label(sensors_frame, text="NO DATA", fg=COLOR_UNKNOWN, width=8)
            value_label.grid(row=row, column=1, padx=3)
            self.value_labels[channel.name] = value_label

            column = 2
            if channel.indicator:
                indicator_label = tk.Label(sensors_frame, text="?", width=2, font=("", 12, "bold"))
                indicator_label.grid(row=row, column=column)
                self.indicator_labels[channel.name] = indicator_label
                column += 1

            self.alarm_labels[channel.name] = {}
            for key in (LOW, HIGH):
                if key not in self.alarms[channel.name]:
                    continue
                level = channel.low_alarm if key == LOW else channel.high_alarm
                text = f"{'<' if key == LOW else '>'} {level:g}"
                label = tk.Label(sensors_frame, text=text, fg=COLOR_IDLE, relief="ridge", width=7)
                label.grid(row=row, column=column, padx=1, pady=1)
                ToolTip(label, f"Alarm when {channel.name} goes {'below' if key == LOW else 'above'}"
                               f" {level:g} {channel.unit}")
                self.alarm_labels[channel.name][key] = label
                column += 1
        return sensors_frame

    def create_outputs_frame(self, frame):
        outputs_frame = tk.LabelFrame(frame, text="Relays")
        for row, output in enumerate(self.outputs):
            name_label = tk.Label(outputs_frame, text=f"{output.name}:", anchor="e", width=14)
            name_label.grid(row=row, column=0, sticky="e")
            ToolTip(name_label, output.description)

            state_label = tk.Label(outputs_frame, text="??", fg=COLOR_UNKNOWN, width=7,
                                   font=("", 10, "bold"))
            state_label.grid(row=row, column=1, padx=3)
            self.output_labels[output.name] = state_label

            on_button = tk.Button(outputs_frame, text=output.on_text, width=6,
                                  command=lambda o=output: self.issue_command(self.set_output, o, True))
            off_button = tk.Button(outputs_frame, text=output.off_text, width=6,
                                   command=lambda o=output: self.issue_command(self.set_output, o, False))
            on_button.grid(row=row, column=2, padx=1, pady=1)
            off_button.grid(row=row, column=3, padx=1, pady=1)
            self.output_buttons += [on_button, off_button]
            if self.read_only:
                on_button.config(state="disabled")
                off_button.config(state="disabled")
        return outputs_frame

    # ------------------------------------------------------------ hardware (thread)
    def read_values(self):
        # Runs on the read_values background thread: only touch the device and the
        # channel states here. Widgets are updated by update_gui(), on the main thread.
        start = time.monotonic()
        try:
            # the outputs first and on every cycle: this is the watchdog keep-alive
            for output in self.outputs:
                self.read_output(output)
            every = max(1, int(self.config_params.get("analog_read_every", 1)))
            if self.cycle % every == 0:
                for channel in self.analog_channels:
                    self.read_analog_channel(channel)
        except ConnectionError as e:
            # no answer at all (bridge server or serial link): the other channels
            # would fail the same way, so count it once, for the whole device
            if self.handle_read_failure(None, f"Could not read {self.device.name}: {e}"):
                for channel in self.analog_channels:
                    self.channels_state[channel.name].set_state(failed_channel_reading())
                for output in self.outputs:
                    self.channels_state[output.name].set_state(failed_output_reading())
            return
        finally:
            self.cycle += 1
        self.handle_read_recovery(None, f"{self.device.name} is answering again")
        self.check_cycle_time(time.monotonic() - start)

    def read_output(self, output):
        try:
            on = self.device.get_output(output)
        except ArduinoIOError as e:
            # the Arduino answered, but not for this output
            if not self.handle_read_failure(output.name, f"Could not read {output.name}: {e}"):
                return
            values = failed_output_reading()
        else:
            self.handle_read_recovery(output.name, f"{output.name} is answering again")
            values = {"on": on, "comm_ok": True}

        previous = self.channels_state[output.name].get_values()
        self.channels_state[output.name].set_state(values)

        commanded = self.commanded_outputs.pop(output.name, None)
        if values["comm_ok"] and commanded is not None and values["on"] != commanded:
            self.logger.warning(f"{self.device.name}: {output.name} was switched"
                                f" {output.on_text if commanded else output.off_text}, but it"
                                f" reads {self.output_state_text(output, values['on'])}")
        elif commanded is None and previous.get("comm_ok") and values["comm_ok"] \
                and previous.get("on") is not None and values["on"] is not None \
                and previous["on"] != values["on"]:
            # a change that was not commanded from here: the watchdog of the firmware
            # (the Arduino went without commands for too long), or another slow control
            self.logger.warning(f"{self.device.name}: {output.name} changed to"
                                f" {self.output_state_text(output, values['on'])} without"
                                f" being commanded from this slow control")

    @staticmethod
    def output_state_text(output, on):
        if on is None:
            return "an unknown state"
        return output.on_text if on else output.off_text

    def read_analog_channel(self, channel):
        try:
            values = self.device.read_channel(channel)
        except ArduinoIOError as e:
            if not self.handle_read_failure(channel.name, f"Could not read {channel.name}: {e}"):
                return
            values = failed_channel_reading()
        else:
            self.handle_read_recovery(channel.name, f"{channel.name} is answering again")
            values = {"value": values["value"], "comm_ok": True}
        self.channels_state[channel.name].set_state(values)
        if values["comm_ok"]:
            self.check_alarms(channel, values["value"])

    def check_alarms(self, channel, value):
        text = f"{self.device.name} {channel.name} ({channel.description})"
        value_text = f"{value:.{channel.precision}f} {channel.unit}"
        alarms = self.alarms[channel.name]
        if LOW in alarms:
            active = value < channel.low_alarm
            self.log_alarm_transition(
                alarms[LOW], active,
                f"{text}: ALARM, {value_text} below {channel.low_alarm:g} {channel.unit}",
                f"{text}: back above {channel.low_alarm:g} {channel.unit} ({value_text})",
            )
            alarms[LOW] = active
        if HIGH in alarms:
            active = value > channel.high_alarm
            self.log_alarm_transition(
                alarms[HIGH], active,
                f"{text}: ALARM, {value_text} above {channel.high_alarm:g} {channel.unit}",
                f"{text}: back below {channel.high_alarm:g} {channel.unit} ({value_text})",
            )
            alarms[HIGH] = active

    def check_cycle_time(self, duration):
        if duration > SLOW_CYCLE_TIME and not self.slow_cycle_warned:
            self.slow_cycle_warned = True
            self.logger.warning(
                f"{self.device.name}: a read cycle took {duration:.2f} s, too close to the"
                f" {WATCHDOG_TIMEOUT:g} s watchdog of the Arduino, which switches the outputs"
                f" off without commands. Increase 'analog_read_every' in the advanced options."
            )
        elif duration < 0.5 * SLOW_CYCLE_TIME:
            self.slow_cycle_warned = False

    @write_command
    def set_output(self, output, on):
        self.device.set_output(output, on)
        # checked by the next read_output(), which runs on this same command thread
        self.commanded_outputs[output.name] = bool(on)
        self.logger.info(f"{self.device.name}: {output.name} switched"
                         f" {output.on_text if on else output.off_text}")

    # ------------------------------------------------------------- GUI (Tk thread)
    def update_gui(self):
        for channel in self.analog_channels:
            self.update_channel_widgets(channel, self.channels_state[channel.name].get_values())
        for output in self.outputs:
            self.update_output_widgets(output, self.channels_state[output.name].get_values())

    def update_channel_widgets(self, channel, values):
        alarms = self.alarms[channel.name]
        for key, label in self.alarm_labels[channel.name].items():
            label.config(fg=COLOR_ALARM if alarms[key] else COLOR_IDLE)

        if not values.get("comm_ok", False):
            self.value_labels[channel.name].config(text="NO DATA", fg=COLOR_UNKNOWN)
            if channel.name in self.indicator_labels:
                self.indicator_labels[channel.name].config(text="?", fg=COLOR_UNKNOWN)
            return

        value = values["value"]
        self.value_labels[channel.name].config(
            text=f"{value:.{channel.precision}f}",
            fg=COLOR_ALARM if any(alarms.values()) else COLOR_OK,
        )
        if channel.name in self.indicator_labels:
            for bound, text, color in channel.indicator:
                if value > bound:
                    self.indicator_labels[channel.name].config(text=text, fg=color)
                    break

    def update_output_widgets(self, output, values):
        label = self.output_labels[output.name]
        if not values.get("comm_ok", False):
            label.config(text="NO DATA", fg=COLOR_UNKNOWN)
        elif values["on"] is None:
            label.config(text="??", fg=COLOR_UNKNOWN)
        elif values["on"]:
            label.config(text=output.on_text, fg=COLOR_ON)
        else:
            label.config(text=output.off_text, fg=COLOR_OFF)


def main():
    configs = {config.name.split()[0].lower(): config for config in ARDUINOS} # gas, electronics
    parser = argparse.ArgumentParser(description="Arduino I/O GUI (gas panel / electronics Arduinos)")
    parser.add_argument("--which", choices=sorted(configs), default="gas",
                        help="Which Arduino (default: gas)")
    parser.add_argument("--host", type=str, default=None,
                        help="Host of the bridge server (default: the one of the Arduino)")
    parser.add_argument("--port", type=int, default=None,
                        help="TCP port of the bridge server (default: the one of the Arduino)")
    parser.add_argument("--read-only", action="store_true", help="Do not allow switching the relays")
    parser.add_argument("--test", action="store_true", help="Use a simulated device for testing")
    args = parser.parse_args()

    config = configs[args.which]
    if args.test:
        from trexdmsc.simulators import ArduinoIOSimulator
        device = ArduinoIOSimulator(config)
    else:
        device = ArduinoIO(config, host=args.host, port=args.port)

    ArduinoIOGUI(device=device, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
