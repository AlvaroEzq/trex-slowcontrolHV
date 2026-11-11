import argparse
import logging
import tkinter as tk

from trexdmsc.gui.base.multidevicegui import MultiDeviceGUI

# Colours of the sidebar. They only affect the navigation chrome of the SuperGUI,
# not the subsystems themselves (which keep the default Tk look).
SIDEBAR_WIDTH = 170
SIDEBAR_BG = "#2b2f38"
SIDEBAR_FG = "#c8ccd4"
SIDEBAR_TITLE_FG = "#8a93a3"
SELECTED_BG = "#3d4757"
SELECTED_FG = "#ffffff"


class SuperGUI:
    """
    Top level GUI containing several subsystems (MultiDeviceGUI), such as HV or gas.

    It provides the sidebar navigation between the subsystems and owns the only
    GUI update scheduler of the application: on every tick, just the currently
    displayed subsystem updates its widgets. The hidden subsystems keep their
    hardware acquisition, state updates and logging running: the visibility only
    controls the GUI rendering.

    Parameters:
    - subsystems (dict): {name: factory or MultiDeviceGUI}. A factory is a callable
        receiving the content frame of the SuperGUI and returning a MultiDeviceGUI
        built with parent_frame=<that frame> and auto_gui_update=False.
    - title (str): Title of the application window.
    - gui_update_time (float): Period, in seconds, of the global GUI update loop.
    """

    def __init__(self, subsystems=None, title="Slow Control", gui_update_time=1):
        self.gui_update_time = gui_update_time
        self.subsystems = {}
        self.current_subsystem = None
        self.current_name = None
        self.buttons = {}

        self.logger = logging.getLogger("app.supergui")

        self.root = tk.Tk()
        self.root.title(title)

        self.sidebar_frame = tk.Frame(self.root, bg=SIDEBAR_BG, width=SIDEBAR_WIDTH,
                                      bd=0, highlightthickness=0)
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False) # keep the width of the sidebar fixed
        tk.Label(self.sidebar_frame, text="SUBSYSTEMS", font=("", 9, "bold"),
                 bg=SIDEBAR_BG, fg=SIDEBAR_TITLE_FG, anchor="w").pack(
            side="top", fill="x", padx=16, pady=(14, 8)
        )

        self.content_frame = tk.Frame(self.root)
        self.content_frame.pack(side="right", fill="both", expand=True)
        # all the subsystem frames are stacked in the same cell, so tkraise() switches between them
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        for name, subsystem in (subsystems or {}).items():
            self.add_subsystem(name, subsystem)

        if self.subsystems and self.current_subsystem is None:
            self.show_subsystem(next(iter(self.subsystems)))

        self.schedule_gui_update()

    def add_subsystem(self, name, subsystem):
        """Add a subsystem, given either as a MultiDeviceGUI or as a factory of one."""
        if callable(subsystem) and not isinstance(subsystem, MultiDeviceGUI):
            subsystem = subsystem(self.content_frame)
        if not isinstance(subsystem, MultiDeviceGUI):
            raise TypeError(f"Subsystem '{name}' is not a MultiDeviceGUI instance")
        if subsystem.root is not self.root:
            raise ValueError(
                f"Subsystem '{name}' does not belong to the SuperGUI window. "
                "Build it with parent_frame=<the content frame given to the factory>."
            )
        if subsystem.auto_gui_update:
            self.logger.warning(
                f"Subsystem '{name}' owns its own GUI update scheduler. Create it with "
                "auto_gui_update=False to let the SuperGUI handle its GUI updates."
            )

        subsystem.frame.grid(row=0, column=0, sticky="nsew")
        subsystem.is_visible = False
        self.subsystems[name] = subsystem

        button = tk.Button(
            self.sidebar_frame, text=name, command=lambda n=name: self.show_subsystem(n),
            bg=SIDEBAR_BG, fg=SIDEBAR_FG, activebackground=SELECTED_BG, activeforeground=SELECTED_FG,
            relief="flat", bd=0, highlightthickness=0, anchor="w", padx=16, pady=10, cursor="hand2",
        )
        button.pack(side="top", fill="x")
        # highlight the button under the pointer, without losing the selected one
        button.bind("<Enter>", lambda event, b=button: b.config(bg=SELECTED_BG, fg=SELECTED_FG))
        button.bind("<Leave>", lambda event, b=button, n=name: self.paint_button(b, n))
        self.buttons[name] = button
        return subsystem

    def paint_button(self, button, name):
        """Paint a sidebar button as selected or not, depending on what is shown."""
        selected = name == self.current_name
        button.config(bg=SELECTED_BG if selected else SIDEBAR_BG,
                      fg=SELECTED_FG if selected else SIDEBAR_FG)

    def show_subsystem(self, name):
        """Display the given subsystem. Only the GUI rendering is affected."""
        subsystem = self.subsystems[name]
        if self.current_subsystem is subsystem:
            return

        if self.current_subsystem is not None:
            self.current_subsystem.is_visible = False

        subsystem.frame.tkraise()
        subsystem.is_visible = True
        self.current_subsystem = subsystem
        self.current_name = name

        # show the menu bar of the subsystem being displayed
        self.root.config(menu=subsystem.menu_bar)

        for button_name, button in self.buttons.items():
            self.paint_button(button, button_name)

        # refresh right away instead of waiting for the next tick
        self.update_gui()

    def update_gui(self):
        """Update the widgets of the currently displayed subsystem only."""
        if self.current_subsystem is None:
            return
        try:
            self.current_subsystem.update_gui()
        except Exception as e:
            self.logger.debug(f"Error updating GUI of subsystem {self.current_name}: {e}")

    def schedule_gui_update(self):
        """The only GUI update loop of the application."""
        self.update_gui()
        self.root.after(
            int(self.gui_update_time * 1000), # convert s to ms
            self.schedule_gui_update
        )

    def run(self):
        try:
            self.root.mainloop()
        finally:
            for subsystem in self.subsystems.values():
                subsystem.close()
        for subsystem in self.subsystems.values():
            subsystem.cleanup()


def main():
    from trexdmsc.core.check import load_checks_or_exit
    from trexdmsc.core.devicesconfig import (add_devices_config_argument, exit_on_config_error,
                                             load_devices_config)
    from trexdmsc.devices import build
    from trexdmsc.gui.subsystems.hv import HVGUI
    from trexdmsc.gui.subsystems.flammablegas import FlammableGasGUI, build_flammable_gas_devices
    from trexdmsc.gui.subsystems.gas import GasGUI, build_gas_devices
    from trexdmsc.gui.subsystems.electronics import ElectronicsGUI, build_electronics_devices

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Enable test mode")
    add_devices_config_argument(parser)
    parser.add_argument("--checks", type=str, help="Select checks configuration file", default="config/checks_config.toml")
    parser.add_argument("--read-only", action="store_true",
                        help="Disable the commands of the gas and electronics subsystems (setpoints and relays)")
    args = parser.parse_args()

    checks_caen, checks_spellman, checks_multidevice = load_checks_or_exit(
        args.checks, "caen", "spellman", "multidevice")

    config = load_devices_config(args)
    with exit_on_config_error():
        spellman_module = build.build_spellman(config, args.test)
        daq_metrics_fetcher = build.build_daq_metrics_fetcher(config, args.test)
        flammable_gas_devices = build_flammable_gas_devices(config, args.test)
        gas_devices = build_gas_devices(config, args.test)
        electronics_devices = build_electronics_devices(config, args.test)
        caen_context = build.open_caen_module(config, args.test)
    log = not args.test

    with caen_context as caen_module:
        subsystems = {
            # each subsystem is built inside the content frame of the SuperGUI and
            # without its own scheduler: the SuperGUI owns the only GUI update loop
            "HV": lambda frame: HVGUI(
                caen_module=caen_module,
                spellman_module=spellman_module,
                daq_metrics_fetcher=daq_metrics_fetcher,
                checks_caen=checks_caen,
                checks_spellman=checks_spellman,
                checks_multidevice=checks_multidevice,
                log=log,
                parent_frame=frame,
                auto_gui_update=False,
            ),
            "Flammable gas": lambda frame: FlammableGasGUI(
                **flammable_gas_devices,
                log=log,
                parent_frame=frame,
                auto_gui_update=False,
            ),
            "Gas": lambda frame: GasGUI(
                **gas_devices,
                log=log,
                parent_frame=frame,
                auto_gui_update=False,
                read_only=args.read_only,
            ),
            "Electronics": lambda frame: ElectronicsGUI(
                **electronics_devices,
                log=log,
                parent_frame=frame,
                auto_gui_update=False,
                read_only=args.read_only,
            ),
        }
        SuperGUI(subsystems, title="TREX Slow Control").run()


if __name__ == "__main__":
    main()
