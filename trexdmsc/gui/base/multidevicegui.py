import tkinter as tk
import logging
from abc import ABC, abstractmethod


class MultiDeviceGUI(ABC):
    """
    A GUI class grouping several device GUIs (based on DeviceGUI) of a subsystem.

    As for DeviceGUI, the hardware acquisition of every child device GUI is
    completely independent from the GUI rendering: the children background
    threads keep reading and logging regardless of whether this subsystem is
    being rendered or not.

    Parameters:
    - name (str): Name of the subsystem (used for the window title and the logger).
    - devices (optional): The device objects of this subsystem.
    - parent_frame (optional): The parent widget in which this GUI places its own frame.
        If None, the GUI is standalone: it creates its own Tk root and runs the mainloop.
    - auto_gui_update (bool): Whether this GUI owns its own GUI update scheduler
        (default: True). Set it to False when it is managed by a parent GUI
        (e.g. a SuperGUI), which then becomes responsible for calling update_gui().
        It never affects the background hardware reading of the children nor the logging.
    - gui_update_time (float): Period, in seconds, of the GUI update loop owned by
        this GUI (only relevant if auto_gui_update is True).
    - log (bool): Whether to log the channels (default: True).

    The child DeviceGUIs must be created inside create_gui() with
    auto_gui_update=False (so that there is a single GUI scheduler for the whole
    subsystem) and registered in self.all_guis.
    """

    def __init__(self, name: str, devices=None, parent_frame=None,
                 auto_gui_update=True, gui_update_time=1, log=True, **kwargs):
        self.name = name
        self.devices = devices if devices is not None else []
        # children GUIs ({name: DeviceGUI}). A subclass may have filled it already.
        if getattr(self, "all_guis", None) is None:
            self.all_guis = {}
        self.logging_enabled = log

        self.gui_update_time = gui_update_time
        # Whether this GUI owns its GUI update scheduler. It does not affect the
        # background hardware reading of the children (which always runs).
        self.auto_gui_update = auto_gui_update
        self.is_visible = True

        # Initialize GUI basic components.
        # self.root is always the actual Tk root/application context, while
        # self.frame is the widget container owned by this GUI.
        self.standalone = parent_frame is None
        if self.standalone:
            self.root = tk.Tk()
            self.root.title(f"{self.name} GUI")
            self.parent_frame = self.root
        else:
            self.parent_frame = parent_frame
            self.root = parent_frame.winfo_toplevel()

        self.frame = tk.Frame(self.parent_frame)
        if self.standalone:
            self.frame.pack(fill="both", expand=True)
        # when managed, the parent GUI is the one placing self.frame in its content area

        if getattr(self, "logger", None) is None:
            self.logger = logging.getLogger(f"app.{self.name}")

        # menu bar. It is only attached to the window if this GUI owns it (standalone).
        # Otherwise, the parent GUI attaches it whenever this subsystem is the visible one.
        self.menu_bar = tk.Menu(self.root)

        # Create GUI
        self.create_gui()

        if self.standalone:
            self.root.config(menu=self.menu_bar)

        self.warn_about_children_schedulers()

        if self.auto_gui_update:
            self.schedule_gui_update()
        if self.standalone:
            self.root.mainloop() # this will block the main thread until the window is closed
            self.cleanup()

    def warn_about_children_schedulers(self):
        """Warn if a child GUI also owns a scheduler (redundant after() callbacks)."""
        for name, gui in self.all_guis.items():
            if getattr(gui, "auto_gui_update", False):
                self.logger.warning(
                    f"GUI '{name}' of {self.name} owns its own GUI update scheduler. "
                    "Create it with auto_gui_update=False to let "
                    f"{type(self).__name__} handle its GUI updates."
                )

    def schedule_gui_update(self):
        """GUI update loop owned by this GUI (standalone mode only)."""
        if not self.auto_gui_update:
            return # the GUI update is handled by the parent GUI

        self.update_gui()
        self.root.after(
            int(self.gui_update_time * 1000), # convert s to ms
            self.schedule_gui_update
        )

    def update_gui(self):
        """Update the widgets of every child GUI. Must NOT talk to the hardware."""
        for name, gui in self.all_guis.items():
            if not hasattr(gui, "update_gui"):
                continue
            try:
                gui.update_gui()
            except Exception as e:
                self.logger.debug(f"Error updating GUI for device {name}: {e}")

    def add_devicegui_config_menu(self):
        """Add the Config > Device GUI configuration entry to the menu bar."""
        self.menu_config = tk.Menu(self.menu_bar, tearoff=0)
        self.menu_config.add_command(label="Device GUI configuration",
                                     command=self.open_devicegui_config_window)
        self.menu_bar.add_cascade(label="Config", menu=self.menu_config)

    def open_devicegui_config_window(self):
        """Window with the advanced options (config_params) of every child GUI."""
        new_window = tk.Toplevel(self.root)
        new_window.title("Device GUI Configuration")

        row = 0
        for name, gui in self.all_guis.copy().items():
            if getattr(gui, "config_params", None) is None:
                continue
            device_frame = tk.LabelFrame(new_window, text=name, font=("", 12, "bold"))
            device_frame.grid(row=row, column=0, sticky="w", padx=10, pady=5)
            gui.make_config_menu(device_frame)
            row += 1

    def cleanup(self):
        """Hook called after the mainloop ends when this GUI is standalone."""
        pass

    @abstractmethod
    def create_gui(self):
        """Create the widgets of this subsystem inside self.frame.

        The children DeviceGUIs must be created with parent_frame inside
        self.frame and auto_gui_update=False, and registered in self.all_guis.
        """
        pass
