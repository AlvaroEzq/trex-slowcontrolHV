from dataclasses import dataclass
from typing import Optional

from trexdmsc.devices.bridge import BridgeClient

# Raspberry Pi of the gas panel, where the bridge servers of the three Bronkhorsts
# (and of the gas Arduino) run (servers/bronkhorstServer*.py of the old slow control)
GAS_PANEL_HOST = "192.168.15.100"

# ProPar integer values: 32000 is 100% of the full scale of the instrument. The value
# travels as an unsigned 16 bit word, and the instrument can go from -23593 to 41942
# (-73.7% to 131%), so the words above 41942 are the negative values.
RAW_FULL_SCALE = 32000
RAW_MAX = 41942


class BronkhorstError(ConnectionError):
    """The instrument answered with a ProPar error status."""


@dataclass(frozen=True)
class BronkhorstConfig:
    """
    Configuration of one Bronkhorst of the gas panel. The instrument cannot tell its
    role in the installation, so it lives here, next to the driver.

    - name: name of the device in the slow control (GUI, logs and log files).
    - description: role in the gas circuit.
    - port: TCP port of its bridge server on the gas panel Raspberry Pi.
    - measure_tag / setpoint_tag: P&ID tags of the measurement and the setpoint.
    - unit, full_scale: engineering unit of the value and its value at 32000 (100%).
    - controller: False for a meter, which has no setpoint.
    - setpoint_min / setpoint_max: accepted setpoints (setpoint_max None: full_scale).
    - precision: decimals shown and logged.
    - log_threshold: change of the measurement that gets a new row in the log file.
    - max_alarm: alarm when the measurement goes above this value (None: no alarm).
    - setpoint_margin_alarm: alarm when the measurement stays above the setpoint by
      more than this margin (None: no alarm).
    """
    name: str
    description: str
    port: int
    measure_tag: str
    unit: str
    full_scale: float
    controller: bool = True
    setpoint_tag: str = ""
    node: int = 3
    setpoint_min: float = 0.0
    setpoint_max: Optional[float] = None
    precision: int = 2
    log_threshold: float = 0.01
    max_alarm: Optional[float] = None
    setpoint_margin_alarm: Optional[float] = None

    @property
    def max_setpoint(self):
        return self.full_scale if self.setpoint_max is None else self.setpoint_max


# The instruments of the gas panel, with the alarm levels of the safety checks of the
# old slow control (OP1, OP2, GL1).
BRONKHORST_P = BronkhorstConfig(
    name="Bronkhorst P",
    description="Pressure controller (CpBp)",
    port=50002,
    measure_tag="PT41",
    setpoint_tag="PCV41",
    unit="bar(a)",
    full_scale=10.0,
    log_threshold=0.01,
    max_alarm=10.1,
    setpoint_margin_alarm=0.2,
)
BRONKHORST_Q = BronkhorstConfig(
    name="Bronkhorst Q",
    description="Flow controller (Cfin)",
    port=50003,
    measure_tag="FQT40",
    setpoint_tag="FQC40",
    unit="ln/h",
    full_scale=60.0,
    log_threshold=0.1,
    setpoint_margin_alarm=1.0,
)
BRONKHORST_M = BronkhorstConfig(
    name="Bronkhorst M",
    description="Flow meter (MfoutD)",
    port=50004,
    measure_tag="QT41",
    unit="ln/h",
    full_scale=60.0,
    controller=False,
    log_threshold=0.1,
)
BRONKHORSTS = (BRONKHORST_P, BRONKHORST_Q, BRONKHORST_M)

# ProPar parameters (process 1)
PARAMETER_MEASURE = 0
PARAMETER_SETPOINT = 1


class Bronkhorst:
    """
    A Bronkhorst EL-FLOW/EL-PRESS instrument of the gas panel, reached through its
    bridge server with the ProPar ASCII protocol.

    ASCII message: ':' length node command [process parameter [value]] '\\r\\n'
    (hexadecimal digits). The frames are the ones of the old slow control
    (slowcontrol/bronkhorst*Module.py).
    """

    def __init__(self, config: BronkhorstConfig, host=GAS_PANEL_HOST, port=None, timeout=2):
        self.config = config
        self.name = config.name
        self.bridge = BridgeClient(host, config.port if port is None else port,
                                   timeout=timeout, name=config.name)

    # ---- conversions
    def to_units(self, raw: int) -> float:
        return raw * self.config.full_scale / RAW_FULL_SCALE

    def to_raw(self, value: float) -> int:
        return int(round(value * RAW_FULL_SCALE / self.config.full_scale))

    # ---- ProPar messages
    def _send(self, body: str) -> str:
        answer = self.bridge.send_recv(f":{body}\r\n".encode("ascii"))
        text = answer.decode("ascii", errors="replace").strip()
        if not text.startswith(":") or len(text) < 9:
            raise BronkhorstError(f"{self.name}: unexpected answer {text!r}")
        return text

    def _check_status(self, text: str):
        # status message: ':04' node '00' status index
        if text[5:7] == "00" and text[7:9] != "00":
            raise BronkhorstError(f"{self.name}: ProPar error status {text[7:9]} ({text!r})")

    def read_parameter_raw(self, parameter: int) -> int:
        """Read an integer parameter of process 1 (0: measure, 1: setpoint)."""
        # command 04 (request parameter): answer as process 1 / parameter 1 integer,
        # from process 1 / parameter 'parameter' integer (0x20 = integer type)
        text = self._send(f"06{self.config.node:02X}04" f"0121" f"01{0x20 | parameter:02X}")
        self._check_status(text)
        if text[5:7] != "02" or len(text) < 15:
            raise BronkhorstError(f"{self.name}: unexpected answer {text!r}")
        raw = int(text[11:15], 16)
        if raw > RAW_MAX:
            raw -= 0x10000 # negative values travel as the complement word
        return raw

    def write_setpoint_raw(self, raw: int):
        raw = min(max(int(raw), 0), RAW_FULL_SCALE)
        # command 01 (send parameter with status answer), process 1, parameter 1 integer
        text = self._send(f"06{self.config.node:02X}01" f"0121" f"{raw:04X}")
        if text[7:9] != "00":
            raise BronkhorstError(f"{self.name}: setpoint {raw} rejected, status {text[7:9]} ({text!r})")

    # ---- values in engineering units
    def read_measure(self) -> float:
        return self.to_units(self.read_parameter_raw(PARAMETER_MEASURE))

    def read_setpoint(self) -> float:
        return self.to_units(self.read_parameter_raw(PARAMETER_SETPOINT))

    def set_setpoint(self, value: float):
        """Write a setpoint in engineering units, within the configured limits."""
        if not self.config.controller:
            raise ValueError(f"{self.name} is a meter, it has no setpoint")
        if not self.config.setpoint_min <= value <= self.config.max_setpoint:
            raise ValueError(f"{self.name}: setpoint {value} {self.config.unit} out of"
                             f" [{self.config.setpoint_min}, {self.config.max_setpoint}]")
        self.write_setpoint_raw(self.to_raw(value))

    def read(self) -> dict:
        """Measurement (and setpoint for a controller) in engineering units."""
        values = {"measure": self.read_measure()}
        if self.config.controller:
            values["setpoint"] = self.read_setpoint()
        return values

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
