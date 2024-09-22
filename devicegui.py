import tkinter as tk
import queue
import threading
import time
from abc import ABC, abstractmethod

from logger import ChannelState

class DeviceGUI(ABC):
    """
    A GUI class for controlling a single device.

    Parameters:
    - device: The device object to control.
    - channels_name (list): A list of channel names.
    - parent_frame (optional): The parent frame for the GUI.
    - **kwargs: for more customization options:
        - log (bool): Whether to log the channels (default: True).
        - channel_state_save_previous (bool): Whether to save the previous channel state (default: True).
        - channel_state_diff_vmon (float): Voltage log monitoring threshold (default: 0.5).
        - channel_state_diff_imon (float): Current log monitoring threshold (default: 0.01).
        - channel_state_prec_vmon (int): Voltage precision (default: 1).
        - channel_state_prec_imon (int): Current precision (default: 3).
        - read_loop_time (float): Time interval for reading channel data (default: 1 second).
    """

    def __init__(self, device, channels_name: list, parent_frame=None, **kwargs):
        self.device = device
        self.channels_name = channels_name
        self.channels_state = None

        self.logging_enabled: bool = kwargs.get("logging_enabled", True)
        self.channels_state_save_previous: bool = kwargs.get("channel_state_save_previous", True)
        self.channels_state_diff_vmon: float = kwargs.get("channel_state_diff_vmon", 0.5)
        self.channels_state_diff_imon: float = kwargs.get("channel_state_diff_imon", 0.01)
        self.channels_state_prec_vmon: int = kwargs.get("channel_state_prec_vmon", 1)
        self.channels_state_prec_imon: int = kwargs.get("channel_state_prec_imon", 3)
        self.read_loop_time: float = kwargs.get("read_loop_time", 1)

        # Validate input parameters
        if not isinstance(self.logging_enabled, bool):
            raise ValueError("logging_enabled must be a boolean")
        if not isinstance(self.channels_state_save_previous, bool):
            raise ValueError("channels_state_save_previous must be a boolean")
        if not isinstance(self.channels_state_prec_vmon, int) or self.channels_state_prec_vmon < 0:
            raise ValueError("channels_state_prec_vmon must be a positive integer")
        if not isinstance(self.channels_state_prec_imon, int) or self.channels_state_prec_imon < 0:
            raise ValueError("channels_state_prec_imon must be a positive integer")
        if not isinstance(self.channels_state_diff_vmon, (int, float)) or self.channels_state_diff_vmon < 0:
            raise ValueError("channels_state_diff_vmon must be a positive number")
        if not isinstance(self.channels_state_diff_imon, (int, float)) or self.channels_state_diff_imon < 0:
            raise ValueError("channels_state_diff_imon must be a positive number")
        if not isinstance(self.read_loop_time, (int, float)) or self.read_loop_time <= 0:
            raise ValueError("read_loop_time must be a positive number")

        # Initialize channel states
        if self.channels_state is None:
            self.channels_state = [
                ChannelState(
                    name,
                    diff_vmon=self.channels_state_diff_vmon,
                    diff_imon=self.channels_state_diff_imon,
                    precision_vmon=self.channels_state_prec_vmon,
                    precision_imon=self.channels_state_prec_imon,
                )
                for name in self.channels_name
            ]

        # Initialize GUI basic components
        start_mainloop = False
        if parent_frame is None:
            self.root = tk.Tk()
            self.root.title(f"{device.name} GUI")
            start_mainloop = True
        else:
            self.root = parent_frame
        
        self.command_queue = queue.Queue()
        self.device_lock = threading.Lock()

        self.create_gui()
        self.start_background_threads()

        if start_mainloop:
            self.root.mainloop() # this will block the main thread until the window is closed

    def process_commands(self):
        while True:
            func, args, kwargs = self.command_queue.get()
            with self.device_lock:
                func(*args, **kwargs)
            self.command_queue.task_done()
            if self.root.cget("cursor") == "watch" and func.__name__ != "read_values":
                self.root.config(cursor="")

    def issue_command(self, func, *args, **kwargs):
        # do not stack read_values commands (critical if reading values is slow)
        if (
            func.__name__ == "read_values"
            and (func, args, kwargs) in self.command_queue.queue
        ):
            return
        # print('\n'), [print(i) for i in self.command_queue.queue] # debug
        self.command_queue.put((func, args, kwargs))
        if (
            func.__name__ != "read_values"
        ):  # because it is constantly reading values in the background
            self.root.config(cursor="watch")
            self.root.update()

    def start_background_threads(self):
        threading.Thread(target=self.read_loop, daemon=True).start()
        threading.Thread(target=self.process_commands, daemon=True).start()

    def read_loop(self):
        while True:
            self.issue_command(self.read_values)
            if self.logging_enabled:
                for chstate in self.channels_state:
                    chstate.save_state(save_previous=self.channels_state_save_previous)
            time.sleep(self.read_loop_time)
    
    @abstractmethod
    def read_values(self):
        pass
    
    @abstractmethod
    def create_gui(self):
        pass


        
