import argparse
import tkinter as tk

from trexdmsc.core.devicesconfig import (add_devices_config_argument, exit_on_config_error,
                                         is_disabled, load_devices_config)
from trexdmsc.devices import build
from trexdmsc.gui.devices import arduinoio as arduinoiogui
from trexdmsc.gui.devices import bronkhorst as bronkhorstgui
from trexdmsc.gui.devices import maxigauge as maxigaugegui
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI
from trexdmsc.gui.base.widgets import disabled_device_frame


class GasGUI(MultiDeviceGUI):
    """
    Subsystem GUI of the gas system: the gas circuit (Bronkhorst pressure controller,
    flow controller and flow meter, and the gas panel Arduino with the pressure and
    temperature transmitters, the pump relay and the pneumatic valve) and the vacuum
    gauges (MaxiGauge).

    It is usable on its own (it then owns the Tk root, the menu bar and the GUI
    update loop) or embedded in a SuperGUI (auto_gui_update=False, and the
    SuperGUI calls update_gui() while this subsystem is the visible one).

    Parameters:
    - bronkhorst_devices (optional): The Bronkhorsts, in the order they are shown
        (gas flow order: pressure controller, then flow controller and flow meter).
    - gas_arduino_device (optional): The Arduino of the gas panel.
    - maxigauge_device (optional): The MaxiGauge.
    - read_only (bool): Disable all the commands (setpoints and relays), e.g. to
        monitor the gas system while another slow control is controlling it.

    A device can be a DisabledDevice (disabled in the devices configuration file):
    a greyed DISABLED frame is shown in its place.
    """

    def __init__(self, bronkhorst_devices=(), gas_arduino_device=None, maxigauge_device=None,
                 parent_frame=None, auto_gui_update=True, gui_update_time=1, log=True,
                 read_only=False):
        self.bronkhorst_devices = tuple(bronkhorst_devices)
        self.gas_arduino_device = gas_arduino_device
        self.maxigauge_device = maxigauge_device
        self.read_only = read_only

        self.bronkhorst_guis = []
        self.gas_arduino_gui = None
        self.maxigauge_gui = None

        super().__init__(name="TREX Gas",
                         devices=[*self.bronkhorst_devices, gas_arduino_device, maxigauge_device],
                         parent_frame=parent_frame,
                         auto_gui_update=auto_gui_update,
                         gui_update_time=gui_update_time,
                         log=log)

    def create_gui(self):
        # the children device GUIs are created with auto_gui_update=False: this
        # subsystem owns the GUI update of all of them.
        # Their frames are packed without fill nor expand so that each device GUI
        # keeps its natural size instead of being stretched over the whole frame
        # (which is as large as the window when the subsystem is shown by a SuperGUI).
        self.add_devicegui_config_menu()

        title = "Gas circuit" + (" (read-only)" if self.read_only else "")
        circuit_frame = tk.LabelFrame(self.frame, text=title, font=("", 14), labelanchor="n")
        circuit_frame.pack(side="left", anchor="n", padx=5, pady=5)

        # the Bronkhorsts first (pressure controller, flow controller and flow meter),
        # then the transmitters, pump and valve of the gas panel Arduino
        for device in self.bronkhorst_devices:
            self.add_bronkhorst_gui(circuit_frame, device)
        if is_disabled(self.gas_arduino_device):
            disabled_device_frame(circuit_frame, self.gas_arduino_device.name, self.gas_arduino_device.reason).pack(
                side="top", anchor="n", fill="x", padx=5, pady=3)
        elif self.gas_arduino_device is not None:
            frame = tk.Frame(circuit_frame)
            frame.pack(side="top", anchor="n", fill="x", padx=5, pady=3)
            self.gas_arduino_gui = arduinoiogui.ArduinoIOGUI(
                device=self.gas_arduino_device,
                parent_frame=frame,
                log=self.logging_enabled,
                auto_gui_update=False,
                read_only=self.read_only,
            )
            self.all_guis[self.gas_arduino_device.name] = self.gas_arduino_gui

        if self.maxigauge_device is not None:
            vacuum_frame = tk.LabelFrame(self.frame, text="Vacuum", font=("", 14), labelanchor="n")
            vacuum_frame.pack(side="left", anchor="n", padx=5, pady=5)
            if is_disabled(self.maxigauge_device):
                disabled_device_frame(vacuum_frame, self.maxigauge_device.name, self.maxigauge_device.reason).pack(
                    side="top", anchor="n", fill="x", padx=5, pady=3)
                return
            frame = tk.Frame(vacuum_frame)
            frame.pack(side="top", anchor="n", padx=5, pady=3)
            self.maxigauge_gui = maxigaugegui.MaxiGaugeGUI(
                device=self.maxigauge_device,
                parent_frame=frame,
                log=self.logging_enabled,
                auto_gui_update=False,
            )
            self.all_guis[self.maxigauge_device.name] = self.maxigauge_gui

    def add_bronkhorst_gui(self, parent, device):
        if is_disabled(device):
            disabled_device_frame(parent, device.name, device.reason).pack(side="top", anchor="n", fill="x",
                                                            padx=5, pady=3)
            return
        frame = tk.Frame(parent)
        frame.pack(side="top", anchor="n", fill="x", padx=5, pady=3)
        gui = bronkhorstgui.BronkhorstGUI(
            device=device,
            parent_frame=frame,
            log=self.logging_enabled,
            auto_gui_update=False,
            read_only=self.read_only,
        )
        self.bronkhorst_guis.append(gui)
        self.all_guis[device.name] = gui


def build_gas_devices(config, test=False):
    """
    Create the devices of the gas subsystem from the devices configuration (the
    simulators if test is True, DisabledDevices for the disabled ones).
    """
    p = build.build_bronkhorst(config, "P", test)
    q = build.build_bronkhorst(config, "Q", test)
    # the flow meter simulator follows the flow controller simulator
    m = build.build_bronkhorst(config, "M", test, source=None if is_disabled(q) else q)
    return {
        "bronkhorst_devices": (p, m, q), # the order they are shown in
        "gas_arduino_device": build.build_arduinoio(config, "gas", test),
        "maxigauge_device": build.build_maxigauge(config, test),
    }


def main():
    parser = argparse.ArgumentParser(description="GUI of the gas system (gas circuit and vacuum)")
    add_devices_config_argument(parser)
    parser.add_argument("--read-only", action="store_true", help="Disable setpoints and relay commands")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    config = load_devices_config(args)
    with exit_on_config_error():
        devices = build_gas_devices(config, test=args.test)
    GasGUI(**devices, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
