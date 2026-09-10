import tkinter as tk
import queue
import threading
import time
import logging
from abc import ABC, abstractmethod

from devicegui import DeviceGUI
from logger import ChannelState, configure_basic_logger
from utilsgui import validate_numeric_entry_input

class MultiDeviceGUI(ABC):
    """
    A GUI class for controlling multiple devices which GUIs are based on DeviceGUI.

    Parameters:
    - devices: A list of device objects to control.
    - channels_name (list): A list of channel names.
    - parent_frame (optional): The parent frame for the GUI.
    - **kwargs: for more customization options:
        - log (bool): Whether to log the channels (default: True).
    """
    
    def __init__(self,name:str, devices, parent_frame=None, log=True, **kwargs):
        self.name = name
        self.all_guis = {}
        self.is_visible = False # so we only update the GUI when it is visible, to save resources
        
    
        # Initialize GUI basic components
        start_mainloop = False
        if parent_frame is None:
            self.root = tk.Tk()
            try:
                title = f"{self.name} GUI"
            except AttributeError:
                title = "Unknown Multi Device GUI"
            self.root.title(title)
            """
            # menu bar only if it is the main gui
            self.menu_bar = tk.Menu(self.root)
            self.menu_config = tk.Menu(self.menu_bar, tearoff=0)
            # self.menu_config.add_command(label="Load checks") # TODO: implement load checks
            self.menu_config.add_command(label="Advanced options", command=self.open_config_menu)
            self.menu_bar.add_cascade(label="Config", menu=self.menu_config)
            self.root.config(menu=self.menu_bar)
            """
            start_mainloop = True
        else:
            self.root = parent_frame
    
        # Create GUI
        self.create_gui()
        self.schedule_gui_update()
        for name, gui in self.all_guis.items():
            if isinstance(gui, DeviceGUI):
                gui.auto_gui_update = False # handle the GUI update for all devices in this MultiDeviceGUI to save after callbacks
        if start_mainloop:
            self.root.mainloop() # this will block the main thread until the window is closed
        
    def schedule_gui_update(self):
        if not self.is_visible:
            return # stop updating GUI

        self.update_gui()
        self.root.after(1000, self.schedule_gui_update) # update every second
    
    def update_gui(self):
        for name, gui in self.all_guis.items():
            if isinstance(gui, DeviceGUI):
                try:
                    gui.update_gui()
                except Exception as e:
                    print(f"Error updating GUI for device {name}: {e}") # TODO: change for a self.logger ??