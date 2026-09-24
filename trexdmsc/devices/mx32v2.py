from dataclasses import dataclass

from pymodbus.client import ModbusSerialClient


# ============================================================
# Sensor configuration
# ============================================================
# The MX32v2 does not report how it is configured, so the configuration of the
# installation is described here and used by the GUI (mx32v2gui.py) to know which
# sensors to poll and what the three alarm bits of each one mean.

def calculate_sensor_address(line, sensor_number=0, digital=True):
    """
    Modbus address of a sensor, as defined in the manual:
    - Digital: (line - 1) * 32 + slave number
    - Analog: 256 + line number
    """
    if digital:
        return (line - 1) * 32 + sensor_number
    return 256 + line


@dataclass(frozen=True)
class AlarmConfig:
    """One of the three alarm thresholds configured in a sensor."""
    number: int    # 1, 2 or 3: matches the alarm bits of the status register
    level: float   # threshold, in the units of the sensor

    @property
    def key(self):
        """Key of this alarm in the dict returned by MX32v2.read_status()."""
        return f"alarm{self.number}"

    def __str__(self):
        return f"A{self.number}"


@dataclass(frozen=True)
class SensorConfig:
    """A sensor connected to the MX32v2 and how it is configured."""
    name: str
    line: int
    digital: bool = False
    sensor_number: int = 0       # only used by digital sensors
    range_max: float = 100.0     # full scale, used to scale the raw measurement
    unit: str = "%LEL"
    alarms: tuple = ()
    log_threshold: float = 0.5   # change (in 'unit') that triggers a line in the log

    @property
    def address(self):
        return calculate_sensor_address(self.line, self.sensor_number, self.digital)


# Levels (%LEL) of the three alarms configured in both analog sensors
LEL_ALARM_LEVELS = (15.0, 30.0, 50.0)

def lel_alarms(levels=LEL_ALARM_LEVELS):
    return tuple(
        AlarmConfig(number=i + 1, level=level) for i, level in enumerate(levels)
    )

# The installation: one analog sensor per line, each with the same three alarms.
SENSORS = (
    SensorConfig(name="Line 1", line=1, digital=False, alarms=lel_alarms()),
    SensorConfig(name="Line 2", line=2, digital=False, alarms=lel_alarms()),
)

# Every magnitude read from a sensor, in the order they are written to the log file.
SENSOR_VALUE_NAMES = (
    "concentration",
    "alarm1",
    "alarm2",
    "alarm3",
    "under_range",
    "over_range",
    "fault",
    "out_of_range",
    "maintenance",
    "comm_ok",
)

def failed_sensor_reading():
    """
    Placeholder reading for a sensor that could not be read.

    The flags are left False and 'comm_ok' is False so that an unknown state is
    never displayed as a confirmed alarm nor as a confirmed OK: whoever reads
    these values has to look at 'comm_ok' first.
    """
    values = {name: False for name in SENSOR_VALUE_NAMES}
    values["concentration"] = -1.0
    return values


# ============================================================
# Device
# ============================================================

class MX32v2:
    def __init__(self, port, baudrate=9600, slave_id=0, timeout=1, name="MX32v2"):
        self.name = name
        self.port = port
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=timeout
        )
        self.slave_id = slave_id

    def connect(self):
        return self.client.connect()

    def close(self):
        self.client.close()

    def open(self):
        """Open the connection, raising if the port could not be opened."""
        if not self.connect():
            raise ConnectionError(f"Could not open the Modbus connection on {self.port}")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


    def read_registers(self, address, count=1):
        response = self.client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.slave_id
        )

        if response.isError():
            raise Exception(f"Error Modbus: {response}")

        return response.registers


    def read_raw_measurement(self, sensor_address):
        """
        Lee valor raw (sin escalar)
        Dirección base: 2000 + sensor_address
        """
        address = 2000 + sensor_address
        return self.read_registers(address, 1)[0]

    def read_measurement(self, sensor_address, range_max):
        """
        Devuelve valor escalado
        Fórmula del manual:
        valor_real = (dato * rango) / 10000
        """
        raw = self.read_raw_measurement(sensor_address)
        value = (raw * range_max) / 10000.0
        return value


    def read_status(self, sensor_address):
        """
        Dirección base: 2300 + sensor_address
        """
        address = 2300 + sensor_address
        value = self.read_registers(address, 1)[0]

        return {
            "alarm1": bool(value & (1 << 0)),
            "alarm2": bool(value & (1 << 1)),
            "alarm3": bool(value & (1 << 2)),
            "under_range": bool(value & (1 << 3)),
            "over_range": bool(value & (1 << 4)),
            "fault": bool(value & (1 << 5)),
            "out_of_range": bool(value & (1 << 6)),
            "maintenance": bool(value & (1 << 7)),
        }

    def read_sensor(self, sensor: SensorConfig):
        """Measurement and status flags of a configured sensor, in one dict."""
        values = {
            "concentration": self.read_measurement(sensor.address, sensor.range_max),
            "comm_ok": True,
        }
        values.update(self.read_status(sensor.address))
        return values


    @staticmethod
    def calculate_sensor_address(line, sensor_number, digital=True):
        """
        Según manual:
        - Digital: (línea - 1) * 32 + nº esclavo
        - Analógico: 256 + nº línea
        """
        return calculate_sensor_address(line, sensor_number, digital)
