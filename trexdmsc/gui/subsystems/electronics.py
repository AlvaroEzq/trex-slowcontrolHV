import argparse
import tkinter as tk

from trexdmsc.core.devicesconfig import (add_devices_config_argument, exit_on_config_error,
                                         is_disabled, load_devices_config)
from trexdmsc.devices import build
from trexdmsc.gui.devices import arduinoio as arduinoiogui
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI
from trexdmsc.gui.base.widgets import disabled_device_frame


class ElectronicsGUI(MultiDeviceGUI):
    """
    Subsystem GUI of the electronics: the Arduino with the relays of the electronics
    power supplies and the Hall current sensors.

    It is usable on its own (it then owns the Tk root, the menu bar and the GUI
    update loop) or embedded in a SuperGUI (auto_gui_update=False, and the
    SuperGUI calls update_gui() while this subsystem is the visible one).

    Parameters:
    - electronics_arduino_device (optional): The Arduino of the electronics.
    - read_only (bool): Disable the relay commands, e.g. to monitor the relays while
        another slow control is controlling them.

    A device can be a DisabledDevice (disabled in the devices configuration file):
    a greyed DISABLED frame is shown in its place.
    """

    def __init__(self, electronics_arduino_device=None, parent_frame=None, auto_gui_update=True,
                 gui_update_time=1, log=True, read_only=False):
        self.electronics_arduino_device = electronics_arduino_device
        self.electronics_arduino_gui = None
        self.read_only = read_only

        super().__init__(name="TREX Electronics",
                         devices=[electronics_arduino_device],
                         parent_frame=parent_frame,
                         auto_gui_update=auto_gui_update,
                         gui_update_time=gui_update_time,
                         log=log)

    def create_gui(self):
        self.add_devicegui_config_menu()

        # the child device GUI is created with auto_gui_update=False: this subsystem
        # owns its GUI update. Its frame is packed without fill nor expand so that it
        # keeps its natural size.
        if is_disabled(self.electronics_arduino_device):
            disabled_device_frame(self.frame, self.electronics_arduino_device.name).pack(
                side="left", anchor="n", padx=5, pady=5)
        elif self.electronics_arduino_device is not None:
            frame = tk.Frame(self.frame)
            frame.pack(side="left", anchor="n", padx=5, pady=5)
            self.electronics_arduino_gui = arduinoiogui.ArduinoIOGUI(
                device=self.electronics_arduino_device,
                parent_frame=frame,
                log=self.logging_enabled,
                auto_gui_update=False,
                read_only=self.read_only,
            )
            self.all_guis[self.electronics_arduino_device.name] = self.electronics_arduino_gui


def build_electronics_devices(config, test=False):
    """
    Create the devices of the electronics subsystem from the devices configuration
    (the simulators if test is True, DisabledDevices for the disabled ones).
    """
    return {"electronics_arduino_device": build.build_arduinoio(config, "electronics", test)}


def main():
    parser = argparse.ArgumentParser(description="GUI of the electronics (power supply relays and Hall sensors)")
    add_devices_config_argument(parser)
    parser.add_argument("--read-only", action="store_true", help="Disable the relay commands")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    config = load_devices_config(args)
    with exit_on_config_error():
        devices = build_electronics_devices(config, test=args.test)
    ElectronicsGUI(**devices, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
