import argparse
import tkinter as tk

import arduinogui
import mx32v2gui
from multidevicegui import MultiDeviceGUI


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
        # the children device GUIs are created with auto_gui_update=False: this
        # subsystem owns the GUI update of all of them.
        # Their frames are packed without fill nor expand so that each device GUI
        # keeps its natural size instead of being stretched over the whole frame
        # (which is as large as the window when the subsystem is shown by a SuperGUI).
        if self.mx32_device is not None:
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

        if self.arduino_device is not None:
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GUI of the flammable gas (isobutane) safety system")
    parser.add_argument("--mx32-port", type=str, default="/dev/ttyUSB1", help="Serial port of the MX32v2")
    parser.add_argument("--mx32-baudrate", type=int, default=9600, help="Modbus baudrate of the MX32v2 (default: 9600)")
    parser.add_argument("--mx32-slave-id", type=int, default=0, help="Modbus slave number of the MX32v2 (default: 0)")
    parser.add_argument("--arduino-port", type=str, default="/dev/ttyACM0", help="Serial port of the Arduino")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    if args.test:
        from simulators import ArduinoSimulator, MX32v2Simulator
        mx32_device = MX32v2Simulator()
        arduino_device = ArduinoSimulator()
        log = False
    else:
        from arduino import ArduinoReader
        from mx32v2 import MX32v2
        mx32_device = MX32v2(port=args.mx32_port, baudrate=args.mx32_baudrate, slave_id=args.mx32_slave_id)
        arduino_device = ArduinoReader(port=args.arduino_port)
        log = True

    FlammableGasGUI(mx32_device=mx32_device, arduino_device=arduino_device, log=log)
