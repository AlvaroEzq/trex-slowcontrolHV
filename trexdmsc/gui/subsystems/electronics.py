import argparse
import tkinter as tk

from trexdmsc.devices.bridge import VACUUM_ELECTRONICS_HOST
from trexdmsc.gui.devices import arduinoio as arduinoiogui
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI


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
        if self.electronics_arduino_device is not None:
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


def build_electronics_devices(test=False, host=VACUUM_ELECTRONICS_HOST):
    """Create the devices of the electronics subsystem (the simulators if test is True)."""
    from trexdmsc.devices.arduinoio import ELECTRONICS_ARDUINO

    if test:
        from trexdmsc.simulators import ArduinoIOSimulator
        # around the levels of the Hall sensors of the old slow control (2.58-2.69 V)
        nominal = {channel.name: voltage for channel, voltage in
                   zip(ELECTRONICS_ARDUINO.analog_channels, (2.75, 2.75, 2.62, 2.40))}
        return {"electronics_arduino_device": ArduinoIOSimulator(ELECTRONICS_ARDUINO, nominal_values=nominal)}

    from trexdmsc.devices.arduinoio import ArduinoIO
    return {"electronics_arduino_device": ArduinoIO(ELECTRONICS_ARDUINO, host=host)}


def main():
    parser = argparse.ArgumentParser(description="GUI of the electronics relays and current sensors")
    parser.add_argument("--host", type=str, default=VACUUM_ELECTRONICS_HOST,
                        help=f"Host of the electronics Arduino bridge server (default: {VACUUM_ELECTRONICS_HOST})")
    parser.add_argument("--read-only", action="store_true", help="Disable the relay commands")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    devices = build_electronics_devices(test=args.test, host=args.host)
    ElectronicsGUI(**devices, read_only=args.read_only, log=not args.test)


if __name__ == "__main__":
    main()
