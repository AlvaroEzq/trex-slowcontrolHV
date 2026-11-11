"""
Creation of the devices from the devices configuration file (see
trexdmsc.core.devicesconfig), shared by the subsystem GUIs, the SuperGUI and the
single-device commands.

Every builder returns the device, its simulator in test mode, or a DisabledDevice
when it is disabled in the file (except for the single-device commands, which pass
standalone=True to start it anyway).
"""
import contextlib

from trexdmsc.core.devicesconfig import DisabledDevice, is_disabled


# ------------------------------------------------------------------ HV subsystem
def open_caen_module(config, test=False, standalone=False):
    """
    Context manager giving the CAEN module (board 0): it keeps the serial port of the
    CAEN open until the end of the 'with' block. The configuration is read right away,
    so that its errors are raised by this call, not when entering the block.
    """
    def create(config, key):
        return config.get(key, "port") # opened by _open_caen_module()

    def simulator():
        from trexdmsc.simulators import ModuleSimulator
        return ModuleSimulator(4, trip_probability=0)

    device = config.build("caen", "CAEN", create, simulator, test, standalone)
    if is_disabled(device) or test:
        return contextlib.nullcontext(device)
    return _open_caen_module(port=device)


@contextlib.contextmanager
def _open_caen_module(port):
    import hvps
    with hvps.Caen(port=port) as caen:
        print("CAEN port:", caen.port)
        print("CAEN baudrate:", caen.baudrate)
        yield caen.module(0)


def build_spellman(config, test=False, standalone=False):
    def create(config, key):
        from trexdmsc.devices.spellman import Spellman
        return Spellman(config.get(key, "host"), config.get(key, "port"))

    def simulator():
        from trexdmsc.simulators import SpellmanSimulator
        return SpellmanSimulator()

    return config.build("spellman", "Spellman SL30", create, simulator, test, standalone)


def build_daq_metrics_fetcher(config, test=False, standalone=False):
    """
    The SSH fetcher of the DAQ metrics. There is no simulator: also used in test mode.
    The SSH user and key come from [daq_ssh] of the credentials file: without them
    the DAQ metrics are not used (DisabledDevice).
    """
    def create(config, key):
        from trexdmsc.core.credentials import credentials_section
        from trexdmsc.devices.daqmetrics import MetricsFetcherSSH
        ssh = credentials_section("daq_ssh")
        if not ssh.get("username"):
            print("No [daq_ssh] username in the credentials file: DAQ metrics disabled")
            return DisabledDevice("DAQ metrics", reason="no [daq_ssh] credentials")
        return MetricsFetcherSSH(
            url=config.get(key, "url"),
            hostname=config.get(key, "host"),
            username=ssh["username"],
            key_filename=ssh.get("key_filename"),
        )

    return config.build("daq_metrics", "DAQ metrics", create, lambda: create(config, "daq_metrics"),
                        test, standalone)


# ------------------------------------------------------- flammable gas subsystem
def build_mx32v2(config, test=False, standalone=False):
    def create(config, key):
        from trexdmsc.devices.mx32v2 import MX32v2
        return MX32v2(port=config.get(key, "port"), baudrate=config.get(key, "baudrate"),
                      slave_id=config.get(key, "slave_id"))

    def simulator():
        from trexdmsc.simulators import MX32v2Simulator
        return MX32v2Simulator()

    return config.build("mx32v2", "MX32v2", create, simulator, test, standalone)


def build_flammable_gas_arduino(config, test=False, standalone=False):
    def create(config, key):
        from trexdmsc.devices.arduino import ArduinoReader
        return ArduinoReader(port=config.get(key, "port"))

    def simulator():
        from trexdmsc.simulators import ArduinoSimulator
        return ArduinoSimulator()

    return config.build("flammable_gas_arduino", "Arduino (safety alarms)", create, simulator,
                        test, standalone)


# ------------------------------------------------------------------ gas subsystem
BRONKHORST_KEYS = {"P": "bronkhorst_p", "Q": "bronkhorst_q", "M": "bronkhorst_m"}


def build_bronkhorst(config, which, test=False, standalone=False, source=None):
    """which: 'P', 'Q' or 'M'. source: the simulator that a flow meter simulator follows."""
    from trexdmsc.devices import bronkhorst
    bronkhorst_config = {"P": bronkhorst.BRONKHORST_P, "Q": bronkhorst.BRONKHORST_Q,
                         "M": bronkhorst.BRONKHORST_M}[which]

    def create(config, key):
        return bronkhorst.Bronkhorst(bronkhorst_config, host=config.get(key, "host"),
                                     port=config.get(key, "port"))

    def simulator():
        from trexdmsc.simulators import BronkhorstSimulator
        return BronkhorstSimulator(bronkhorst_config, source=source)

    return config.build(BRONKHORST_KEYS[which], bronkhorst_config.name, create, simulator,
                        test, standalone)


def build_maxigauge(config, test=False, standalone=False):
    def create(config, key):
        from trexdmsc.devices.maxigauge import MaxiGauge
        return MaxiGauge(host=config.get(key, "host"), port=config.get(key, "port"))

    def simulator():
        from trexdmsc.simulators import MaxiGaugeSimulator
        return MaxiGaugeSimulator()

    return config.build("maxigauge", "MaxiGauge", create, simulator, test, standalone)


# ----------------------------------------------- gas and electronics Arduinos
ARDUINOIO_KEYS = {"gas": "gas_arduino", "electronics": "electronics_arduino"}


def build_arduinoio(config, which, test=False, standalone=False):
    """which: 'gas' (gas panel Arduino) or 'electronics'."""
    from trexdmsc.devices import arduinoio
    arduino_config = {"gas": arduinoio.GAS_ARDUINO, "electronics": arduinoio.ELECTRONICS_ARDUINO}[which]

    def create(config, key):
        return arduinoio.ArduinoIO(arduino_config, host=config.get(key, "host"),
                                   port=config.get(key, "port"))

    def simulator():
        from trexdmsc.simulators import ArduinoIOSimulator
        if which == "electronics":
            # around the levels of the Hall sensors of the old slow control (2.58-2.69 V)
            nominal = {channel.name: voltage for channel, voltage in
                       zip(arduino_config.analog_channels, (2.75, 2.75, 2.62, 2.40))}
            return ArduinoIOSimulator(arduino_config, nominal_values=nominal)
        return ArduinoIOSimulator(arduino_config)

    return config.build(ARDUINOIO_KEYS[which], arduino_config.name, create, simulator,
                        test, standalone)


# ---------------------------------------------------------------- Rigol subsystem
RIGOL_KEYS = {"left": "rigol_left", "right": "rigol_right"}
RIGOL_NAMES = {"left": "Rigol Left", "right": "Rigol Right"}


def build_rigol(config, which, test=False, standalone=False):
    """which: 'left' or 'right'."""
    name = RIGOL_NAMES[which]

    def create(config, key):
        from trexdmsc.devices.rigol import RigolPowerSupply
        return RigolPowerSupply(resource_name=config.get(key, "resource"), name=name)

    def simulator():
        from trexdmsc.simulators import RigolSimulator
        return RigolSimulator(name=f"{name} SIMULATOR")

    return config.build(RIGOL_KEYS[which], name, create, simulator, test, standalone)
