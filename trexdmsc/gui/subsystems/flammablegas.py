import argparse
import tkinter as tk

from trexdmsc.gui.devices import arduino as arduinogui
from trexdmsc.gui.devices import mx32v2 as mx32v2gui
from trexdmsc.core.devicesconfig import (add_devices_config_argument, exit_on_config_error,
                                         is_disabled, load_devices_config)
from trexdmsc.devices import build
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI
from trexdmsc.gui.base.widgets import disabled_device_frame


class FlammableGasGUI(MultiDeviceGUI):
    """
    Subsystem GUI of the sensor and alarm safety system for the use of flammable
    gas (isobutane): the MX32v2 gas sensor controller and the Arduino reading the
    digital alarm signals of the safety system.

    It is usable on its own (it then owns the Tk root, the menu bar and the GUI
    update loop) or embedded in a SuperGUI (auto_gui_update=False, and the
    SuperGUI calls update_gui() while this subsystem is the visible one).

    Parameters:
    - mx32_device (optional): The MX32v2 gas sensor controller.
    - arduino_device (optional): The Arduino reading the alarm signals.
    - sensors (optional): The sensors configured in the MX32v2 (defaults to mx32v2.SENSORS).
    - channel_names (optional): The alarm signals read by the Arduino
        (defaults to arduinogui.CHANNEL_NAMES).

    A device can be a DisabledDevice (disabled in the devices configuration file):
    a greyed DISABLED frame is shown in its place.
    """

    def __init__(self, mx32_device=None, arduino_device=None, sensors=None, channel_names=None,
                 parent_frame=None, auto_gui_update=True, gui_update_time=1, log=True):
        self.mx32_device = mx32_device
        self.mx32_frame = None
        self.mx32_gui = None
        self.sensors = sensors

        self.arduino_device = arduino_device
        self.arduino_frame = None
        self.arduino_gui = None
        self.channel_names = channel_names

        super().__init__(name="TREX Flammable Gas",
                         devices=[mx32_device, arduino_device],
                         parent_frame=parent_frame,
                         auto_gui_update=auto_gui_update,
                         gui_update_time=gui_update_time,
                         log=log)

    def create_gui(self):
        self.add_devicegui_config_menu()

        # the children device GUIs are created with auto_gui_update=False: this
        # subsystem owns the GUI update of all of them.
        # Their frames are packed without fill nor expand so that each device GUI
        # keeps its natural size instead of being stretched over the whole frame
        # (which is as large as the window when the subsystem is shown by a SuperGUI).
        if is_disabled(self.mx32_device):
            disabled_device_frame(self.frame, self.mx32_device.name, self.mx32_device.reason).pack(
                side="left", anchor="n", padx=5, pady=5)
        elif self.mx32_device is not None:
            self.mx32_frame = tk.Frame(self.frame)
            self.mx32_frame.pack(side="left", anchor="n", padx=5, pady=5)
            self.mx32_gui = mx32v2gui.MX32v2GUI(
                device=self.mx32_device,
                parent_frame=self.mx32_frame,
                sensors=self.sensors,
                log=self.logging_enabled,
                auto_gui_update=False,
            )
            self.all_guis[self.mx32_device.name] = self.mx32_gui

        if is_disabled(self.arduino_device):
            disabled_device_frame(self.frame, self.arduino_device.name, self.arduino_device.reason).pack(
                side="left", anchor="n", padx=5, pady=5)
        elif self.arduino_device is not None:
            self.arduino_frame = tk.Frame(self.frame)
            self.arduino_frame.pack(side="left", anchor="n", padx=5, pady=5)
            self.arduino_gui = arduinogui.ArduinoGUI(
                device=self.arduino_device,
                parent_frame=self.arduino_frame,
                channel_names=self.channel_names,
                log=self.logging_enabled,
                auto_gui_update=False,
            )
            self.all_guis[self.arduino_device.name] = self.arduino_gui


def build_flammable_gas_devices(config, test=False):
    """
    Create the devices of the flammable gas subsystem from the devices configuration
    (the simulators if test is True, DisabledDevices for the disabled ones).
    """
    return {
        "mx32_device": build.build_mx32v2(config, test),
        "arduino_device": build.build_flammable_gas_arduino(config, test),
    }


def main():
    parser = argparse.ArgumentParser(description="GUI of the flammable gas (isobutane) safety system")
    add_devices_config_argument(parser)
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    config = load_devices_config(args)
    with exit_on_config_error():
        devices = build_flammable_gas_devices(config, test=args.test)
    FlammableGasGUI(**devices, log=not args.test)


if __name__ == "__main__":
    main()
