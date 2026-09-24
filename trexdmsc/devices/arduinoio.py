from dataclasses import dataclass
from typing import Optional, Tuple

from trexdmsc.devices.bridge import BridgeClient, GAS_PANEL_HOST, VACUUM_ELECTRONICS_HOST

ARDUINO_PORT = 50000
STX = b"\x02"
ETX = b"\x03"

# Pins that the firmware drives together with the 'xsh' / 'xsl' / 'xg3' commands
# (the single pin commands only take one digit, so pins 10-12 can only be used so)
THREE_PINS = (10, 11, 12)

# The firmware drives the output pins 4 to 12 LOW when it has not received any
# command for 1 second (Timer1 watchdog). The GUI must keep talking to it faster.
WATCHDOG_TIMEOUT = 1.0


class ArduinoIOError(ConnectionError):
    """The Arduino answered, but not what was expected."""


@dataclass(frozen=True)
class AnalogChannelConfig:
    """
    An analog input of an Arduino of the slow control.

    - name: name in the slow control (GUI, logs and log files), e.g. the P&ID tag.
    - description: what it measures.
    - input: sensor number of the firmware (1 to 6, 'rs1' reads A0, 'rs6' reads A5).
    - unit: engineering unit of the value.
    - calibration: (x0, y0, x1, y1) linear conversion from ADC counts (0-1023) to the
      value: counts x0 are y0 and counts x1 are y1.
    - precision: decimals shown and logged.
    - log_threshold: change of the value that gets a new row in the log file.
    - low_alarm / high_alarm: alarm when the value goes below / above (None: no alarm).
    - indicator: optional ((lower bound, text, color), ...) shown next to the value:
      the first entry whose bound the value is above is shown, in the given order.
    """
    name: str
    description: str
    input: int
    unit: str
    calibration: Tuple[float, float, float, float] = (0, 0, 1023, 1023)
    precision: int = 2
    log_threshold: float = 0.05
    low_alarm: Optional[float] = None
    high_alarm: Optional[float] = None
    indicator: Tuple[Tuple[float, str, str], ...] = ()

    def to_value(self, counts: int) -> float:
        x0, y0, x1, y1 = self.calibration
        return y0 + (counts - x0) * (y1 - y0) / (x1 - x0)


@dataclass(frozen=True)
class OutputConfig:
    """
    A digital output of an Arduino of the slow control (a relay).

    - name: name in the slow control (GUI, logs and log files).
    - description: what the relay switches.
    - pins: output pins driven together. A single digit pin (4 to 9), or THREE_PINS.
    - inverse: True when the relay is active with the pin LOW. The API works with the
      logical state (on = relay active) and does the inversion.
    - on_text / off_text: names of the two states in the GUI.
    """
    name: str
    description: str
    pins: Tuple[int, ...]
    inverse: bool = False
    on_text: str = "ON"
    off_text: str = "OFF"

    def __post_init__(self):
        if tuple(self.pins) != THREE_PINS and not all(0 <= pin <= 9 for pin in self.pins):
            raise ValueError(f"Output {self.name}: pins must be single digit, or {THREE_PINS}")


@dataclass(frozen=True)
class ArduinoIOConfig:
    """An Arduino of the slow control: where its bridge server is and what it has connected."""
    name: str
    host: str
    port: int = ARDUINO_PORT
    analog_channels: Tuple[AnalogChannelConfig, ...] = ()
    outputs: Tuple[OutputConfig, ...] = ()


def _pressure_transmitter(name, description, input, calibration):
    # old safety check OP2: pressure above 10.1 bar(a)
    return AnalogChannelConfig(name, description, input, "bar(a)", calibration,
                               precision=2, log_threshold=0.02, high_alarm=10.1)


def _temperature_transmitter(name, description, input, calibration, low_alarm):
    # old safety checks OT1 (above 35 C) and OT2 (below -8/-10/-15 C, per sensor)
    return AnalogChannelConfig(name, description, input, "C", calibration,
                               precision=1, log_threshold=0.2,
                               low_alarm=low_alarm, high_alarm=35.0)


# Arduino of the gas panel: pressure and temperature transmitters of the gas circuit
# (calibrations of slowcontrol/trexDM.py of the old slow control), the pump relay and
# the pneumatic valve.
GAS_ARDUINO = ArduinoIOConfig(
    name="Gas Arduino",
    host=GAS_PANEL_HOST,
    analog_channels=(
        _pressure_transmitter("PT40", "Pressure MpinD", 1, (207, 0, 922, 10)),
        _temperature_transmitter("TT40", "Temperature MpinD", 2, (140, -40, 843, 125), low_alarm=-8.0),
        _pressure_transmitter("PT32", "Pressure MhpP", 3, (140, 1, 842, 11)),
        _temperature_transmitter("TT32", "Temperature MhpP", 4, (140, -40, 840, 125), low_alarm=-10.0),
        _pressure_transmitter("PT30", "Pressure MlpP", 5, (140, 1, 843, 11)),
        _temperature_transmitter("TT30", "Temperature MlpP", 6, (140, -40, 843, 125), low_alarm=-15.0),
    ),
    outputs=(
        OutputConfig("Pump", "R1-SC pump relay", THREE_PINS),
        OutputConfig("Valve V40-V46", "Pneumatic valve V40-V46", (4,), on_text="OPEN", off_text="CLOSE"),
    ),
)

# Levels of the Hall current sensors of the old slow control (volts): "an inner
# value means no current"
HALL_INDICATOR = ((2.69, "o", "green"), (2.58, "~", "#d75fd7"), (float("-inf"), "x", "red"))


def _hall_sensor(name, input):
    return AnalogChannelConfig(name, f"Hall current sensor {name}", input, "V", (0, 0, 1023, 5),
                               precision=2, log_threshold=0.02, indicator=HALL_INDICATOR)


# Arduino of the electronics: the relays of the electronics power supplies (active
# with the pin LOW, so a watchdog timeout leaves the electronics on) and the Hall
# current sensors.
ELECTRONICS_ARDUINO = ArduinoIOConfig(
    name="Electronics Arduino",
    host=VACUUM_ELECTRONICS_HOST,
    analog_channels=(
        _hall_sensor("BiPo1", 1),
        _hall_sensor("BiPo2", 2),
        _hall_sensor("RnFree1", 3),
        _hall_sensor("RnFree2", 4),
    ),
    outputs=(
        OutputConfig("Electronic 1", "Electronics relay 1 (Left)", (4,), inverse=True),
        OutputConfig("Electronic 2", "Electronics relay 2 (Left)", (5,), inverse=True),
        OutputConfig("Electronic 3", "Electronics relay 3 (Right)", (6,), inverse=True),
        OutputConfig("Electronic 4", "Electronics relay 4 (Right)", (7,), inverse=True),
    ),
)
ARDUINOS = (GAS_ARDUINO, ELECTRONICS_ARDUINO)


class ArduinoIO:
    """
    An Arduino of the slow control with the trexdm_serial firmware (analog inputs and
    digital outputs), reached through its bridge server (servers/analogArduinoServer.py
    of the old slow control).

    Messages are STX command ETX, and the firmware echoes the command followed by
    ',value' when there is one (the bridge server adds and removes a counter to match
    the answers with the requests). Commands (slowcontrol/analogModule.py):
    - 'rsN': ADC counts of sensor N (1 to 6).
    - 'shD' / 'slD': set pin D (one digit) HIGH / LOW. 'gpD': state of pin D.
    - 'xsh' / 'xsl': set pins 10, 11 and 12 HIGH / LOW. 'xg3': state of those pins.

    Any command resets the watchdog of the firmware, which drives all the outputs LOW
    after WATCHDOG_TIMEOUT seconds without commands.
    """

    def __init__(self, config: ArduinoIOConfig, host=None, port=None, timeout=1):
        self.config = config
        self.name = config.name
        self.bridge = BridgeClient(config.host if host is None else host,
                                   config.port if port is None else port,
                                   timeout=timeout, name=config.name)

    def _command(self, command: str):
        """Send a command, check the echo and return the value of the answer (or None)."""
        answer = self.bridge.send_recv(STX + command.encode("ascii") + ETX)
        fields = answer.strip(STX + ETX).decode("ascii", errors="replace").split(",")
        if fields[0] != command[:3]:
            raise ArduinoIOError(f"{self.name}: answer {answer!r} does not match command {command!r}")
        return fields[1] if len(fields) > 1 else None

    # ---- analog inputs
    def read_analog(self, input: int) -> int:
        """ADC counts (0 to 1023) of sensor 'input' (1 to 6)."""
        if not 1 <= input <= 6:
            raise ValueError(f"Sensor must be 1 to 6, not {input}")
        value = self._command(f"rs{input}")
        try:
            counts = int(value)
        except (TypeError, ValueError):
            counts = -1
        if not 0 <= counts <= 1023:
            raise ArduinoIOError(f"{self.name}: invalid reading {value!r} of sensor {input}")
        return counts

    def read_channel(self, channel: AnalogChannelConfig) -> dict:
        counts = self.read_analog(channel.input)
        return {"value": channel.to_value(counts), "counts": counts}

    # ---- digital outputs
    def _set_pins(self, pins, high: bool):
        if tuple(pins) == THREE_PINS:
            self._command("xsh" if high else "xsl")
        else:
            for pin in pins:
                self._command(f"{'sh' if high else 'sl'}{pin}")

    def _get_pins(self, pins) -> Optional[bool]:
        """True if all the pins are HIGH, False if all are LOW, None otherwise."""
        if tuple(pins) == THREE_PINS:
            states = self._command("xg3") or ""
        else:
            states = "".join(self._command(f"gp{pin}") or "" for pin in pins)
        if states and set(states) == {"1"}:
            return True
        if states and set(states) == {"0"}:
            return False
        return None

    def set_output(self, output: OutputConfig, on: bool):
        """Activate (on=True) or deactivate a relay."""
        self._set_pins(output.pins, bool(on) != output.inverse)

    def get_output(self, output: OutputConfig) -> Optional[bool]:
        """True if the relay is active, False if not, None if its pins disagree."""
        high = self._get_pins(output.pins)
        if high is None:
            return None
        return high != output.inverse

    # no persistent connection (see BridgeClient), same interface as the other devices
    def open(self):
        self.bridge.open()

    def close(self):
        self.bridge.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
