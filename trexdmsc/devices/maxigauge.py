import math
from dataclasses import dataclass
from typing import Optional

from trexdmsc.devices.bridge import BridgeClient, VACUUM_ELECTRONICS_HOST

MAXIGAUGE_PORT = 50001

STX = b"\x02"
ETX = b"\x03"
CR = b"\r"
LF = b"\n"
ENQ = b"\x05"
NAK = b"\x15"

# Status of a gauge in the answer of the PRx command (Pfeiffer TPG 256 A manual)
STATUS_OK = 0
STATUS_NAMES = {
    0: "OK",
    1: "Underrange",
    2: "Overrange",
    3: "Sensor error",
    4: "Sensor off",
    5: "No sensor",
    6: "Identification error",
}
STATUS_SHORT_NAMES = {0: "OK", 1: "Und", 2: "Ove", 3: "Err", 4: "Off", 5: "NS", 6: "IdE"}
NUMBER_OF_CHANNELS = 6


class MaxiGaugeError(ConnectionError):
    """The MaxiGauge did not acknowledge the command, or its answer is not understood."""


@dataclass(frozen=True)
class GaugeConfig:
    """
    Configuration of one channel of the MaxiGauge.

    - channel: channel number, 1 to 6.
    - name: name in the slow control (GUI, logs and log files).
    - tag: P&ID tag of the gauge ("" if it is not installed / has no tag).
    - unit: pressure unit configured in the MaxiGauge.
    - max_alarm: alarm when the pressure goes above this value (None: no alarm).
    - log_fraction: relative change of the pressure that gets a new row in the log file.
    """
    channel: int
    name: str
    tag: str = ""
    unit: str = "mbar"
    max_alarm: Optional[float] = None
    log_fraction: float = 0.05


# Gauges of the installation. The alarm levels are the ones of the safety checks of
# the old slow control (GL5, GL6, GL7).
GAUGES = (
    GaugeConfig(1, "Gas system vacuum", tag="PT31", max_alarm=10.0),
    GaugeConfig(2, "Chamber vacuum", tag="PT71", max_alarm=10.0),
    GaugeConfig(3, "MaxiGauge 3"),
    GaugeConfig(4, "MaxiGauge 4"),
    GaugeConfig(5, "MaxiGauge 5"),
    GaugeConfig(6, "MaxiGauge 6"),
)

GAUGE_VALUE_NAMES = ("pressure", "status", "comm_ok")


def failed_gauge_reading():
    """Placeholder values for a gauge that cannot be read."""
    return {"pressure": math.nan, "status": -1, "comm_ok": False}


class MaxiGauge:
    """
    Pfeiffer MaxiGauge (TPG 256 A) vacuum gauge controller, reached through its bridge
    server.

    The client sends all the lines of a transaction in a single message,
    STX line CR line CR ... ETX, and the server writes them one by one to the serial
    port (each has to be acknowledged by the MaxiGauge with ACK CR LF), and sends back
    the last answer as STX answer ETX. So reading a pressure is STX 'PRx' CR ENQ CR ETX,
    exactly as in the old slow control (slowcontrol/maxiGaugeModule.py).
    """

    def __init__(self, host=VACUUM_ELECTRONICS_HOST, port=MAXIGAUGE_PORT, timeout=3, name="MaxiGauge"):
        self.name = name
        self.bridge = BridgeClient(host, port, timeout=timeout, name=name)

    def _transaction(self, command: str) -> str:
        answer = self.bridge.send_recv(STX + command.encode("ascii") + CR + ENQ + CR + ETX)
        text = answer.strip(STX + ETX + CR + LF)
        if text.startswith(NAK):
            raise MaxiGaugeError(f"{self.name}: command {command!r} not acknowledged (NAK)")
        return text.decode("ascii", errors="replace")

    def read_channel(self, channel: int):
        """Return (status, pressure) of a channel (1 to 6). See STATUS_NAMES."""
        if not 1 <= channel <= NUMBER_OF_CHANNELS:
            raise ValueError(f"Channel must be 1 to {NUMBER_OF_CHANNELS}, not {channel}")
        text = self._transaction(f"PR{channel}")
        try:
            status, pressure = text.split(",")
            return int(status), float(pressure)
        except ValueError as e:
            raise MaxiGaugeError(f"{self.name}: unexpected answer {text!r} to PR{channel}") from e

    def read_gauge(self, gauge: GaugeConfig) -> dict:
        status, pressure = self.read_channel(gauge.channel)
        return {"pressure": pressure, "status": status, "comm_ok": True}

    def sensor_on(self, channel: int):
        """Switch a gauge on, leaving the others unchanged (SEN command)."""
        if not 1 <= channel <= NUMBER_OF_CHANNELS:
            raise ValueError(f"Channel must be 1 to {NUMBER_OF_CHANNELS}, not {channel}")
        states = ["0"] * NUMBER_OF_CHANNELS # 0: no change, 1: off, 2: on
        states[channel - 1] = "2"
        return self._transaction("SEN," + ",".join(states))

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
