import tkinter as tk
import queue
import threading
import time
from abc import ABC, abstractmethod

from logger import ChannelState

class DeviceGUI(ABC):
    def __init__(self, device, channels_name : list, parent_frame=None):
        self.device = device
        self.channels_name = channels_name
        self.channels_state = None
        self.channels_state_save_previous = True
        self.channels_state_diff_vmon = 0.5
        self.channels_state_diff_imon = 0.01
        self.channels_state_prec_vmon = 1
        self.channels_state_prec_imon = 3
        self.read_loop_time = 1 # seconds

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
            self.root.mainloop()

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
        while True:
            self.issue_command(self.read_values)
            for chstate in self.channels_state:
                chstate.save_state(save_previous=self.channels_state_save_previous)
            time.sleep(self.read_loop_time)
    
    @abstractmethod
    def read_values(self):
        pass
    
    @abstractmethod
    def create_gui(self):
        pass


        
