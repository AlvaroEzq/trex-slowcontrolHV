import tkinter as tk
import queue
import threading
import time
import logging
from abc import ABC, abstractmethod

from logger import configure_basic_logger
from utilsgui import validate_numeric_entry_input

# Consecutive failed reads that a device (or one of its sensors) is allowed before
# the failure is reported. A single timeout every few hours is normal and solves
# itself, and at the usual read_loop_time this still reports a real outage in a few
# seconds. Configurable at run time from the advanced options menu.
DEFAULT_READ_FAILURES_TO_WARN = 3

# Seconds that close() waits for the command being run before releasing the device
# anyway, so that a device that does not answer cannot block closing the window.
CLOSE_TIMEOUT = 5

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
        - read_failures_to_warn (int): Consecutive failed reads before a failure is
            reported (default: DEFAULT_READ_FAILURES_TO_WARN).

    Connection handling: read_values() raising one of the connection_errors means the
    device could not be reached. That is not logged with a traceback on every read:
    it is counted by handle_read_failure(), reported once it persists, shown in the
    GUI, and the device gets disconnect_device()/reconnect_device() to recover. The
    subclasses only say which errors are connection errors and, if the device keeps
    a connection open between reads, how to reopen it.
    """

    # exceptions raised by read_values() that mean the device could not be reached.
    # Empty by default: anything raised is then a bug and logged as such.
    connection_errors = ()

    # read_failures key of the device itself, as opposed to one of its sensors/channels
    DEVICE = None

    def __init__(self, device, channels_states, parent_frame=None, auto_gui_update=True, **kwargs):
        self.device = device
        self.channels_state = channels_states.copy()
        self.channels_name = list(channels_states.keys())

        self.config_params = {
            "logging_enabled" : kwargs.get("logging_enabled", True),
            "read_loop_time" : kwargs.get("read_loop_time", 1),
            "gui_update_time" : kwargs.get("gui_update_time", 1),
            "read_failures_to_warn" : kwargs.get("read_failures_to_warn", DEFAULT_READ_FAILURES_TO_WARN),
        }
        # consecutive failed reads, per sensor/channel name (DEVICE: the device itself)
        self.read_failures = {}
        
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

        # some device APIs query the hardware for the name: read it only once
        try:
            self.device_name = device.name
        except AttributeError:
            self.device_name = "unknown device"

        # Initialize GUI basic components.
        # self.root is always the actual Tk root/application context, while
        # self.frame is the widget container owned by this GUI.
        self.standalone = parent_frame is None
        if self.standalone:
            self.root = tk.Tk()
            self.root.title(f"{self.device_name} GUI")
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
        self.closed = False # set by close(): stops the background reading

        # Whether this GUI owns its GUI update scheduler. It does not affect the
        # background hardware reading (which always runs) in any way.
        self.auto_gui_update = auto_gui_update
        self.is_visible = True

        #Initialize logger
        logger_name = f"app.{self.device_name}"
        self.logger = logging.getLogger(logger_name)
        if self.logger.parent.name == "root": # if it is not embedded in another GUI with its own logger
            self.logger = configure_basic_logger(logger_name)
        else:
            pass # use the logger from the parent GUI (because it propagates)

        # Create GUI
        self.create_gui()
        # shown (on top of the GUI) only while the device cannot be reached
        self.connection_label = tk.Label(
            self.frame, text=f"NO COMMUNICATION WITH {self.device_name}",
            fg="white", bg="red", font=("", 12, "bold"),
        )
        # The hardware acquisition always runs, no matter who renders the GUI
        # the background threads talk to tkinter, so they must not start before
        # the main loop is running (otherwise: "main thread is not in main loop")
        self.root.after(0, self.start_background_threads)
        if self.auto_gui_update:
            self.schedule_gui_update()
        if self.standalone:
            try:
                self.root.mainloop() # this will block the main thread until the window is closed
            finally:
                self.close()
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
            if func != self.read_cycle:
                self.schedule_in_main_thread(self.set_cursor, "")

    def issue_command(self, func, *args, **kwargs):
        # do not stack read commands (critical if reading values is slow)
        if (
            func == self.read_cycle
            and (func, args, kwargs) in self.command_queue.queue
        ):
            return
        # print('\n'), [print(i) for i in self.command_queue.queue] # debug
        self.command_queue.put((func, args, kwargs))
        if (
            func != self.read_cycle
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
        while not self.closed:
            try:
                self.issue_command(self.read_cycle)
                if self.config_params["logging_enabled"]:
                    for name, chstate in self.channels_state.items():
                        chstate.save_state(
                            save_previous=self.config_channels_params[name]["save_previous"],
                            force=self.config_channels_params[name]["save_force"],
                        )
            except Exception as e:
                self.logger.exception(f"{self.device.name} read loop failed: {e}")
            time.sleep(self.config_params["read_loop_time"])

    def read_cycle(self):
        """One read of the hardware: read_values() plus the connection handling around it."""
        if self.closed:
            return # do not read (nor reconnect!) a device that has been released
        try:
            if self.read_failures.get(self.DEVICE, 0):
                self.reconnect_device() # the last read could not reach the device
            self.read_values()
        except self.connection_errors as e:
            if self.handle_read_failure(self.DEVICE, f"Could not communicate with {self.device_name}: {e}"):
                self.on_device_lost()
            try:
                self.disconnect_device()
            except Exception as e:
                self.logger.debug(f"Error disconnecting {self.device_name}: {e}")
        else:
            self.handle_read_recovery(self.DEVICE, f"{self.device_name} is answering again")
        finally:
            self.schedule_in_main_thread(self.update_connection_indicator)

    def disconnect_device(self):
        """
        Hook called after a connection error. Devices that keep a connection open
        between reads close it here (it is probably broken). Nothing by default:
        most devices open and close the connection on every read.
        """
        pass

    def reconnect_device(self):
        """
        Hook called before reading again after a connection error. Devices that keep
        a connection open between reads reopen it here, raising one of the
        connection_errors if they cannot. Nothing by default.
        """
        pass

    def on_device_lost(self):
        """
        Hook called on every failed read once the device has been unreachable for
        'read_failures_to_warn' reads, e.g. to mark the values as unknown. Nothing by
        default: the last values read are kept (the GUI shows the device is unreachable).
        """
        pass

    @property
    def device_connected(self):
        """False once the device has been unreachable long enough to be reported."""
        return self.read_failures.get(self.DEVICE, 0) < self.read_failures_to_warn()

    def update_connection_indicator(self):
        try:
            shown = self.connection_label.winfo_manager() != ""
            if self.device_connected and shown:
                self.connection_label.pack_forget()
            elif not self.device_connected and not shown:
                others = [w for w in self.frame.pack_slaves() if w is not self.connection_label]
                if others:
                    self.connection_label.pack(fill="x", before=others[0])
                else:
                    self.connection_label.pack(fill="x")
        except tk.TclError:
            pass # the widget is already destroyed

    def read_failures_to_warn(self):
        return max(1, int(self.config_params.get("read_failures_to_warn",
                                                 DEFAULT_READ_FAILURES_TO_WARN)))

    def handle_read_failure(self, key, message):
        """
        Count a failed read and report it only once it has persisted.

        The first failures are only recorded at debug level, where they do not
        reach the Slack/Mattermost handlers. Once the same key (DEVICE, or one of its
        sensors/channels) has failed 'read_failures_to_warn' reads in a row the
        problem is real and gets logged as a warning, once, until it recovers.

        Returns True when the failure has lasted long enough to be published as a
        failed reading; while it returns False the caller keeps the last values.
        """
        failures = self.read_failures.get(key, 0) + 1
        self.read_failures[key] = failures
        to_warn = self.read_failures_to_warn()

        if failures < to_warn:
            self.logger.debug(f"{message} (failure {failures} of {to_warn}, tolerated)")
            return False
        if failures == to_warn:
            self.logger.warning(f"{message} (failed {failures} reads in a row)")
        else:
            self.logger.debug(message) # already warned about this one
        return True

    def handle_read_recovery(self, key, message):
        """Report a device (or sensor/channel) that reads again, if it was warned about."""
        failures = self.read_failures.pop(key, 0)
        if failures >= self.read_failures_to_warn():
            self.logger.info(f"{message} after {failures} failed reads")
        elif failures:
            self.logger.debug(f"{message} after {failures} failed reads")

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
    
    def close(self):
        """
        Stop reading the device and release it. Called when the window is closed (by
        whoever owns the window), so that a device that keeps its connection open
        (e.g. the CAEN serial port) is not left open, nor reopened by the read loop,
        while the process finishes.
        """
        if self.closed:
            return
        self.closed = True
        # wait for the command being run, if any, but not forever
        locked = self.device_lock.acquire(timeout=CLOSE_TIMEOUT)
        try:
            self.disconnect_device()
        except Exception as e:
            self.logger.debug(f"Error disconnecting {self.device_name}: {e}")
        finally:
            if locked:
                self.device_lock.release()

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


        
