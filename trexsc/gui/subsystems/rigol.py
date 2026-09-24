import argparse
import tkinter as tk

from trexsc.gui.devices import rigol as rigolgui
from trexsc.gui.base.multidevicegui import MultiDeviceGUI


class RigolsGUI(MultiDeviceGUI):
    """
    Subsystem GUI grouping the GUIs of several Rigol power supplies.

    It is usable on its own (it then owns the Tk root, the menu bar and the GUI
    update loop) or embedded in a SuperGUI (auto_gui_update=False, and the
    SuperGUI calls update_gui() while this subsystem is the visible one).
    """

    def __init__(self, devices, channel_names=None, parent_frame=None,
                 auto_gui_update=True, gui_update_time=1, log=True):
        self.channel_names = channel_names if channel_names is not None else {}
        self.device_frames = {}

        super().__init__(name="TREX Rigols",
                         devices=devices,
                         parent_frame=parent_frame,
                         auto_gui_update=auto_gui_update,
                         gui_update_time=gui_update_time,
                         log=log)

    def create_gui(self):
        for device in self.devices:
            if device is None:
                continue
            frame = tk.Frame(self.frame)
            frame.pack(side="top", fill="x", anchor="n", expand=True)
            self.device_frames[device.name] = frame
            self.all_guis[device.name] = rigolgui.RigolGUI(
                device=device,
                parent_frame=frame,
                channel_names=self.channel_names.get(device.name),
                log=self.logging_enabled,
                auto_gui_update=False, # this subsystem owns the GUI update of its devices
            )


def main():
    parser = argparse.ArgumentParser(description="GUI for several Rigol power supplies")
    parser.add_argument("--resource", type=str, action="append", default=[],
                        help="Resource name of a Rigol power supply (repeatable)")
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    if args.test:
        from trexsc.simulators import RigolSimulator
        devices = [RigolSimulator(name="Rigol Left SIMULATOR"), RigolSimulator(name="Rigol Right SIMULATOR")]
    else:
        from trexsc.devices.rigol import RigolPowerSupply
        if not args.resource:
            print("Please provide at least one resource name using --resource")
            exit(1)
        devices = [RigolPowerSupply(name=f"Rigol {i+1}", resource_name=r) for i, r in enumerate(args.resource)]

    RigolsGUI(devices, log=False)


if __name__ == "__main__":
    main()
