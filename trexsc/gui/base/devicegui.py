import tkinter as tk
import queue
import threading
import time
import logging
from abc import ABC, abstractmethod

from trexsc.core.logger import configure_basic_logger
from trexsc.gui.base.widgets import validate_numeric_entry_input

class DeviceGUI(ABC):
    """
    A GUI class for controlling a single device.

    The hardware acquisition (read_values, run from a background thread) is kept
    strictly separated from the GUI rendering (update_gui, run from the Tkinter
    main thread). They only communicate through the channels state.

    Parameters:
    - device: The device object to control.
    - channels_states (dict): A dict of {channel name: ChannelState}.
    - parent_frame (optional): The parent widget in which this GUI places its own frame.
        If None, the GUI is standalone: it creates its own Tk root and runs the mainloop.
    - auto_gui_update (bool): Whether this GUI owns its own GUI update scheduler
        (default: True). Set it to False when the GUI is managed by a parent GUI
        (e.g. a MultiDeviceGUI), which then becomes responsible for calling
        update_gui(). It never affects the background hardware reading nor the logging.
    - **kwargs: for more customization options:
        - log (bool): Whether to log the channels (default: True).
        - channel_state_save_previous (bool): Whether to save the previous channel state (default: True).
        - channel_state_save_force (bool): Whether to force saving all the channel state (default: False).
        - channel_state_diff_vmon (float): Voltage log monitoring threshold (default: 0.5).
        - channel_state_diff_imon (float): Current log monitoring threshold (default: 0.01).
        - channel_state_prec_vmon (int): Voltage precision (default: 1).
        - channel_state_prec_imon (int): Current precision (default: 3).
        - read_loop_time (float): Time interval for reading channel data (default: 1 second).
    """

    def __init__(self, device, channels_states, parent_frame=None, auto_gui_update=True, **kwargs):
        self.device = device
        self.channels_state = channels_states.copy()
        self.channels_name = list(channels_states.keys())

        self.config_params = {
            "logging_enabled" : kwargs.get("logging_enabled", True),
            "read_loop_time" : kwargs.get("read_loop_time", 1),
            "gui_update_time" : kwargs.get("gui_update_time", 1),
        }
        
        base_channel_params = {
            "save_previous": False,
            "save_force": False,
            "thresholds": {},
            "precisions": {},
        }
        
        self.config_channels_params = {}
        for name in self.channels_name:
            self.config_channels_params[name] = base_channel_params.copy()
            if self.channels_state.get(name):
                # if the channel state is already provided, use its parameters as default
                chstate = self.channels_state[name]
                self.config_channels_params[name]["thresholds"] = chstate.thresholds
                self.config_channels_params[name]["precisions"] = chstate.precisions

        # Validate input parameters
        if not isinstance(self.config_params["logging_enabled"], bool):
            raise ValueError("logging_enabled must be a boolean")
        if not isinstance(self.config_params["read_loop_time"], (int, float)) or self.config_params["read_loop_time"] <= 0:
            raise ValueError("read_loop_time must be a positive number")

        # Initialize GUI basic components.
        # self.root is always the actual Tk root/application context, while
        # self.frame is the widget container owned by this GUI.
        self.standalone = parent_frame is None
        if self.standalone:
            self.root = tk.Tk()
            try:
                title = f"{device.name} GUI"
            except AttributeError:
                title = "Unknown device GUI"
            self.root.title(title)
            self.parent_frame = self.root
        else:
            self.parent_frame = parent_frame
            self.root = parent_frame.winfo_toplevel()

        self.frame = tk.Frame(self.parent_frame)
        self.frame.pack(fill="both", expand=True)

        # menu bar. It is only attached to the window if this GUI owns it (standalone).
        # Otherwise, the parent GUI may attach it whenever this GUI is the visible one.
        self.menu_bar = tk.Menu(self.root)
        self.menu_config = tk.Menu(self.menu_bar, tearoff=0)
        # self.menu_config.add_command(label="Load checks") # TODO: implement load checks
        self.menu_config.add_command(label="Advanced options", command=self.open_config_menu)
        self.menu_bar.add_cascade(label="Config", menu=self.menu_config)
        if self.standalone:
            self.root.config(menu=self.menu_bar)

        self.validate_numeric_input = (self.root.register(validate_numeric_entry_input), "%P")
        
        self.command_queue = queue.Queue()
        self.device_lock = threading.Lock()

        # Whether this GUI owns its GUI update scheduler. It does not affect the
        # background hardware reading (which always runs) in any way.
        self.auto_gui_update = auto_gui_update
        self.is_visible = True

        #Initialize logger
        try:
            logger_name = f"app.{self.device.name}"
        except AttributeError:
            logger_name = "app.unknown"
        self.logger = logging.getLogger(logger_name)
        if self.logger.parent.name == "root": # if it is not embedded in another GUI with its own logger
            self.logger = configure_basic_logger(logger_name)
        else:
            pass # use the logger from the parent GUI (because it propagates)

        # Create GUI
        self.create_gui()
        # The hardware acquisition always runs, no matter who renders the GUI
        # the background threads talk to tkinter, so they must not start before
        # the main loop is running (otherwise: "main thread is not in main loop")
        self.root.after(0, self.start_background_threads)
        if self.auto_gui_update:
            self.schedule_gui_update()
        if self.standalone:
            self.root.mainloop() # this will block the main thread until the window is closed
            self.cleanup()

    def schedule_in_main_thread(self, func, *args):
        """Schedule func in the tkinter main loop (tkinter must only be used from it)."""
        try:
            self.root.after(0, func, *args)
        except (RuntimeError, tk.TclError):
            pass # the main loop is not running (GUI starting up or already closed)

    def set_cursor(self, cursor):
        try:
            if self.root.cget("cursor") != cursor:
                self.root.config(cursor=cursor)
        except tk.TclError:
            pass # the widget is already destroyed

    def schedule_in_main_thread(self, func, *args):
        """Schedule func in the tkinter main loop (tkinter must only be used from it)."""
        try:
            self.root.after(0, func, *args)
        except (RuntimeError, tk.TclError):
            pass # the main loop is not running (GUI starting up or already closed)

    def set_cursor(self, cursor):
        try:
            if self.root.cget("cursor") != cursor:
                self.root.config(cursor=cursor)
        except tk.TclError:
            pass # the widget is already destroyed

    def process_commands(self):
        while True:
            func, args, kwargs = self.command_queue.get()
            try:
                with self.device_lock:
                    func(*args, **kwargs)
            except Exception as e:
                self.logger.exception(f"{func.__name__} command failed: {e}")
            finally:
                self.command_queue.task_done()
            if func.__name__ != "read_values":
                self.schedule_in_main_thread(self.set_cursor, "")

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
            self.schedule_in_main_thread(self.set_cursor, "watch")

    def start_background_threads(self):
        threading.Thread(target=self.read_loop, daemon=True).start()
        threading.Thread(target=self.process_commands, daemon=True).start()

    def schedule_gui_update(self):
        """GUI update loop owned by this GUI (standalone mode only)."""
        if not self.auto_gui_update:
            return # the GUI update is handled by the parent GUI

        try:
            self.update_gui()
        except Exception as e:
            self.logger.debug(f"{self.device.name} GUI update failed: {e}")

        self.root.after(
            self.config_params["gui_update_time"]*1000, # convert s to ms
            self.schedule_gui_update
        )

    def read_loop(self):
        while True:
            try:
                self.issue_command(self.read_values)
                if self.config_params["logging_enabled"]:
                    for name, chstate in self.channels_state.items():
                        chstate.save_state(
                            save_previous=self.config_channels_params[name]["save_previous"],
                            force=self.config_channels_params[name]["save_force"],
                        )
            except Exception as e:
                self.logger.exception(f"{self.device.name} read loop failed: {e}")
            time.sleep(self.config_params["read_loop_time"])

    def set_config_param(self, key : str, value):
        if key in self.config_params:
            self.config_params[key] = value
        else:
            print(f"Warning: {key} is not a valid config parameter.")
        return self.config_params.get(key, None)

    def set_config_params(self, config_params : dict):
        for key, value in config_params.items():
            if key in self.config_params:
                self.config_params[key] = value
            else:
                print(f"Warning: {key} is not a valid config parameter.")
        return self.config_params

    def get_config_param(self, key : str):
        return self.config_params.get(key, None)

    def get_config_params(self):
        return self.config_params

    def open_config_menu(self):
        new_window = tk.Toplevel(self.root)
        new_window.title("Configuration")

        self.make_config_menu(new_window)

    def make_config_menu(self, frame):
        row = 0
        config_widgets = {}
        for key, value in self.config_params.items():
            #print(f"key: {key}, value: {value}")
            row += 1
            tk.Label(frame, text=key).grid(row=row, column=1, sticky="w")
            var = None
            if isinstance(value, bool):
                var = tk.BooleanVar()
                var.set(value)
                widget = tk.Checkbutton(frame, variable=var)
            elif isinstance(value, int):
                var = tk.IntVar()
                var.set(value)
                widget = tk.Entry(frame, justify="center", width=5,
                            validate="key", validatecommand=self.validate_numeric_input,
                            textvariable=var)
            elif isinstance(value, float):
                var = tk.DoubleVar()
                var.set(value)
                widget = tk.Entry(frame, justify="center", width=5,
                            validate="key", validatecommand=self.validate_numeric_input,
                            textvariable=var)
            elif isinstance(value, str):
                var = tk.StringVar()
                var.set(value)
                widget = tk.Entry(frame, justify="center", width=5,
                            validate="key", textvariable=var)
            else:
                continue

            widget.grid(row=row, column=2, sticky="w")
            config_widgets[key] = var
        row += 1
        apply_button = tk.Button(frame, text="Apply", command=lambda: apply_settings())
        apply_button.grid(row=row, column=1, sticky="w", pady=5)

        def apply_settings():
            for key, var in config_widgets.items():
                #print(f"key: {key}, value: {var.get()}")
                self.set_config_param(key, var.get())
            #new_window.destroy()
    
    def cleanup(self):
        """Hook called after the mainloop ends when this GUI is standalone."""
        pass

    @abstractmethod
    def read_values(self):
        """Read the hardware and update the internal state. Must NOT touch Tk widgets."""
        pass
    
    @abstractmethod
    def update_gui(self):
        """Update the Tk widgets from the internal state. Must NOT talk to the hardware."""
        pass
    
    @abstractmethod
    def create_gui(self):
        """Create the widgets of this GUI inside self.frame."""
        pass


        
