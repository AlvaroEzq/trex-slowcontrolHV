"""
Devices configuration file: the address of every device and whether it is used.

The file (config/devices_config.toml by default, relative to the working directory)
has one section per device, e.g.

    [bronkhorst_p]
    enabled = true
    host = "192.168.15.100"
    port = 50002

A device with 'enabled = false' is not created nor read by the subsystem GUIs (nor
by the SuperGUI): its place shows a greyed DISABLED frame. The single-device
commands (e.g. trexdm-sc-bronkhorst) only take its address from the file, they
start the device even if it is disabled.
"""
import contextlib

import toml

DEFAULT_DEVICES_CONFIG = "config/devices_config.toml"


class DevicesConfigError(Exception):
    pass


class DisabledDevice:
    """Stands for a device disabled in the devices configuration file."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"DisabledDevice({self.name!r})"


def is_disabled(device):
    return isinstance(device, DisabledDevice)


class DevicesConfig:
    def __init__(self, sections: dict, filename="<dict>"):
        self.sections = sections
        self.filename = filename

    @classmethod
    def load(cls, filename=DEFAULT_DEVICES_CONFIG):
        try:
            sections = toml.load(filename)
        except FileNotFoundError:
            raise DevicesConfigError(
                f"Devices configuration file '{filename}' not found (run from the"
                f" repository root, or give the file with --devices-config)") from None
        except toml.TomlDecodeError as e:
            raise DevicesConfigError(f"Invalid devices configuration file '{filename}': {e}") from None
        return cls(sections, filename)

    def section(self, key) -> dict:
        try:
            section = self.sections[key]
        except KeyError:
            raise DevicesConfigError(f"{self.filename}: missing section [{key}]") from None
        if not isinstance(section, dict):
            raise DevicesConfigError(f"{self.filename}: [{key}] is not a section")
        return section

    def get(self, key, field):
        try:
            return self.section(key)[field]
        except KeyError:
            raise DevicesConfigError(f"{self.filename}: missing '{field}' in [{key}]") from None

    def enabled(self, key) -> bool:
        enabled = self.section(key).get("enabled", True)
        if not isinstance(enabled, bool):
            raise DevicesConfigError(f"{self.filename}: 'enabled' of [{key}] must be true or false")
        return enabled

    def build(self, key, name, create, simulator=None, test=False, standalone=False):
        """
        Create the device of section 'key'.

        - name: name of the device, shown in the DISABLED frame.
        - create: function that creates the real device from this config (it gets
            the DevicesConfig and the section key, and reads the address with get()).
        - simulator: function without arguments that creates its simulator (test mode).
        - standalone: True for the single-device commands, which start the device
            even if it is disabled (they only take its address from the file).

        Returns a DisabledDevice if the device is disabled (and not standalone).
        """
        if not self.enabled(key):
            if not standalone:
                return DisabledDevice(name)
            print(f"Note: [{key}] is disabled in {self.filename}, starting it anyway")
        if test:
            return simulator()
        return create(self, key)


@contextlib.contextmanager
def exit_on_config_error():
    """Turn an error of the devices configuration file into a clean exit with its message."""
    try:
        yield
    except DevicesConfigError as e:
        raise SystemExit(f"Error: {e}") from None


def add_devices_config_argument(parser):
    parser.add_argument("--devices-config", type=str, default=DEFAULT_DEVICES_CONFIG,
                        help="Devices configuration file with their addresses and which"
                             f" ones are enabled (default: {DEFAULT_DEVICES_CONFIG})")


def load_devices_config(args):
    """Load the file given by the --devices-config argument, exiting with a clear message on error."""
    with exit_on_config_error():
        return DevicesConfig.load(args.devices_config)
