import argparse
import tkinter as tk

from trexdmsc.devices.bridge import GAS_PANEL_HOST, VACUUM_ELECTRONICS_HOST
from trexdmsc.gui.devices import arduinoio as arduinoiogui
from trexdmsc.gui.devices import bronkhorst as bronkhorstgui
from trexdmsc.gui.devices import maxigauge as maxigaugegui
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI


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

        # the pressure controller first, then the transmitters, pump and valve of the
        # gas panel Arduino, and the flow controller and meter, as in the old GUI
        devices = list(self.bronkhorst_devices)
        first_bronkhorsts = devices[:1]
        other_bronkhorsts = devices[1:]
        for device in first_bronkhorsts:
            self.add_bronkhorst_gui(circuit_frame, device)
        if self.gas_arduino_device is not None:
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
        for device in other_bronkhorsts:
            self.add_bronkhorst_gui(circuit_frame, device)

        if self.maxigauge_device is not None:
            vacuum_frame = tk.LabelFrame(self.frame, text="Vacuum", font=("", 14), labelanchor="n")
            vacuum_frame.pack(side="left", anchor="n", padx=5, pady=5)
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


def build_gas_devices(test=False, gas_host=GAS_PANEL_HOST, vacuum_host=VACUUM_ELECTRONICS_HOST):
    """Create the devices of the gas subsystem (the simulators if test is True)."""
    from trexdmsc.devices.arduinoio import GAS_ARDUINO
    from trexdmsc.devices.bronkhorst import BRONKHORST_P, BRONKHORST_Q, BRONKHORST_M

    if test:
        from trexdmsc.simulators import ArduinoIOSimulator, BronkhorstSimulator, MaxiGaugeSimulator
        p = BronkhorstSimulator(BRONKHORST_P)
        q = BronkhorstSimulator(BRONKHORST_Q)
        m = BronkhorstSimulator(BRONKHORST_M, source=q) # the flow meter follows the controller
        return {
            "bronkhorst_devices": (p, q, m),
            "gas_arduino_device": ArduinoIOSimulator(GAS_ARDUINO),
            "maxigauge_device": MaxiGaugeSimulator(),
        }

    from trexdmsc.devices.arduinoio import ArduinoIO
    from trexdmsc.devices.bronkhorst import Bronkhorst
    from trexdmsc.devices.maxigauge import MaxiGauge
    return {
        "bronkhorst_devices": tuple(Bronkhorst(config, host=gas_host)
                                    for config in (BRONKHORST_P, BRONKHORST_Q, BRONKHORST_M)),
        "gas_arduino_device": ArduinoIO(GAS_ARDUINO, host=gas_host),
        "maxigauge_device": MaxiGauge(host=vacuum_host),
    }


def main():
    parser = argparse.ArgumentParser(description="GUI of the gas system (gas circuit and vacuum)")
    parser.add_argument("--gas-host", type=str, default=GAS_PANEL_HOST,
                        help=f"Host of the gas panel bridge servers (default: {GAS_PANEL_HOST})")
    parser.add_argument("--vacuum-host", type=str, default=VACUUM_ELECTRONICS_HOST,
                        help=f"Host of the MaxiGauge bridge server (default: {VACUUM_ELECTRONICS_HOST})")
    parser.add_argument("--read-only", action="store_true", help="Disable setpoints and relay commands")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    devices = build_gas_devices(test=args.test, gas_host=args.gas_host, vacuum_host=args.vacuum_host)
    GasGUI(**devices, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
