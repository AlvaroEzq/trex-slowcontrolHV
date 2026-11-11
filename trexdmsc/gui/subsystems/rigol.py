import argparse
import tkinter as tk

from trexdmsc.gui.devices import rigol as rigolgui
from trexdmsc.core.devicesconfig import (add_devices_config_argument, exit_on_config_error,
                                         is_disabled, load_devices_config)
from trexdmsc.devices import build
from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI
from trexdmsc.gui.base.widgets import disabled_device_frame


class RigolsGUI(MultiDeviceGUI):
    """
    Subsystem GUI grouping the GUIs of several Rigol power supplies.

    It is usable on its own (it then owns the Tk root, the menu bar and the GUI
    update loop) or embedded in a SuperGUI (auto_gui_update=False, and the
    SuperGUI calls update_gui() while this subsystem is the visible one).

    A device can be a DisabledDevice (disabled in the devices configuration file):
    a greyed DISABLED frame is shown in its place.
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
            if is_disabled(device):
                disabled_device_frame(self.frame, device.name).pack(side="top", fill="x",
                                                                    anchor="n", padx=5, pady=5)
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
    parser = argparse.ArgumentParser(description="GUI for the Rigol power supplies")
    add_devices_config_argument(parser)
    parser.add_argument("--test", action="store_true", help="Use simulated devices for testing")
    args = parser.parse_args()

    config = load_devices_config(args)
    with exit_on_config_error():
        left = build.build_rigol(config, "left", args.test)
        right = build.build_rigol(config, "right", args.test)
    channel_names = {left.name: rigolgui.CHANNEL_NAMES_LEFT, right.name: rigolgui.CHANNEL_NAMES_RIGHT}
    RigolsGUI([left, right], channel_names=channel_names, log=False)


if __name__ == "__main__":
    main()
