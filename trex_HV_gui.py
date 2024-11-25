import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import time
import argparse
import threading
import sys
import logging

import caengui
import spellmangui
import spellmanClass as spll
import hvps

import utils
from checkframe import ChecksFrame
from check import load_checks_from_toml_file
from utilsgui import PrintToTextWidget, ToolTip, enable_children, validate_numeric_entry_input
from metrics_fetcher import MetricsFetcherSSH
import logger


class HVGUI:
    def __init__(self, caen_module=None, spellman_module=None, checks_caen=None, checks_spellman=None, checks_multidevice=None, log=True):
        if checks_caen is None:
            checks_caen = []
        if checks_spellman is None:
            checks_spellman = []
        if checks_multidevice is None:
            checks_multidevice = []

        self.caen_module = caen_module
        self.caen_frame = None
        self.caen_gui = None
        self.caen_checks = checks_caen

        self.spellman_module = spellman_module
        self.spellman_frame = None
        self.spellman_gui = None
        self.spellman_checks = checks_spellman

        self.checks = checks_multidevice
        self.all_channels = {}
        self.all_guis = {}
        self.channels_gui = {}
        self.channels_vmon_guilabel = {}
        self.channels_vset_guientries = {}
        self.channels_vset_guilabel = {}

        self.logging_enabled = log
        self.multidevice_frame = None
        self.checksframe = None
        self.channel_optmenus = None
        self.vset_entries = None
        self.factor_entries = None
        self.step_entry = None
        self.step_var = None

        self.protocol_stop_flag = False # flag to stop the protocol
        self.protocol_stop_button = None
        self.protocol_thread = None

        # daq metrics variables
        self.metrics_fetcher = None
        self.run_number_label = None
        self.daq_speed_label = None
        self.daq_events_label = None
        self.events_number_label = None
        self.add_to_googlesheet_button = None
        self.add_to_googlesheet_thread = None

        # trip recovery variables
        self.triprec_active = None
        self.trip_detected = True
        self.trip_count = None
        self.trip_count_label = None
        self.max_count_entry = None
        self.triprec_thread = None
        self.triprec_activate_button = None
        self.triprec_desactivate_button = None
        self.triprec_channels = []
        self.triprec_frame = None

        self.logger = logger.configure_basic_logger("app", log_level=logging.DEBUG)

        self.create_gui()

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("TREX HV SC")
        self.validate_numeric_input = (self.root.register(validate_numeric_entry_input), "%P")

        if self.caen_module is not None:
            self.caen_frame = tk.Frame(self.root)
            self.caen_frame.pack(side="left", fill="x", anchor="n", expand=True)
            self.caen_gui = caengui.CaenHVPSGUI(module=self.caen_module, parent_frame=self.caen_frame,
                                                channel_names=caengui.CHANNEL_NAMES, checks=self.caen_checks, silence=False, log=self.logging_enabled)
            self.all_channels = {name: self.caen_module.channels[i] for i, name in enumerate(self.caen_gui.channels_name)}
            self.channels_gui = {name: self.caen_gui for name in self.caen_gui.channels_name}
            self.all_guis['caen'] = self.caen_gui
            self.channels_vmon_guilabel = {name: label for name, label in zip(self.caen_gui.channels_name, self.caen_gui.vmon_labels)}
            self.channels_vset_guientries = {name: entry for name, entry in zip(self.caen_gui.channels_name, self.caen_gui.vset_entries)}
            self.channels_vset_guilabel = {name: label for name, label in zip(self.caen_gui.channels_name, self.caen_gui.vset_labels)}

        if self.spellman_module is not None:
            self.spellman_frame = tk.Frame(self.root)
            self.spellman_frame.pack(side="right", fill=tk.BOTH, expand=True)
            self.spellman_gui = spellmangui.SpellmanFrame(spellman=self.spellman_module, parent=self.spellman_frame, checks=self.spellman_checks, log=self.logging_enabled) # TODO: implement individual spellman checks
            self.all_channels = {'cathode' : self.spellman_module, **self.all_channels} # add the spellman module as cathode at the front of the dict
            self.channels_gui['cathode'] = self.spellman_gui
            self.all_guis['cathode'] = self.spellman_gui
            self.channels_vmon_guilabel['cathode'] = self.spellman_gui.labels['voltage_s']
            self.channels_vset_guientries['cathode'] = self.spellman_gui.labels['voltage_dac_s']
            self.channels_vset_guilabel['cathode'] = self.spellman_gui.labels['voltage_dac_label']


        scrolled_text_frame = self.caen_frame if self.caen_frame else self.root
        # State to track if the widget is hidden
        self.text_visible = False

        # Create the toggle button with a downward triangle (initially visible text)
        self.toggle_button = tk.Button(scrolled_text_frame, text="\u25BC Show terminal output", command=self.toggle_scrolled_text,
                                        font=("Arial", 9), relief="raised", bd=0)
        self.toggle_button.pack(side="top", anchor="nw", pady=0, padx=5)
        self.scrolled_text = ScrolledText(scrolled_text_frame, font=("Arial", "9", "normal"), state="disabled", height=9)
        self.scrolled_text.pack(side="left", fill="both", expand=True, padx=0)
        if self.scrolled_text:
            self.redirect_logging(self.scrolled_text)
            # redirect also the StreamHandler to the scrolled text using the TextWidgetHandler
            while self.logger.hasHandlers() and any([type(h) is logging.StreamHandler for h in self.logger.handlers]):
                self.logger.removeHandler([h for h in self.logger.handlers if type(h) is logging.StreamHandler][0])
            self.logger.addHandler(logger.TextWidgetHandler(self.scrolled_text))
        daq_frame = tk.Frame(scrolled_text_frame)
        daq_frame.pack(side="right", fill="both", expand=True)
        self.create_daq_frame(daq_frame)

        if self.caen_module is not None and self.spellman_module is not None:
            self.create_multidevice_frame(self.spellman_frame)

        self.menu_bar = tk.Menu(self.root)
        self.menu_config = tk.Menu(self.menu_bar, tearoff=0)
        # self.menu_config.add_command(label="Load checks") # TODO: implement load checks
        self.menu_config.add_command(label="Verbose", command=self.open_verbose_window)
        self.menu_bar.add_cascade(label="Config", menu=self.menu_config)
        self.root.config(menu=self.menu_bar)

        self.root.mainloop()
        self.reset_logging()

    def open_verbose_window(self):
        new_window = tk.Toplevel(self.root)
        new_window.title("Verbose")

        loggers = logger.get_children_loggers("app", include_parent=True)
        for l in loggers:
            if not l.handlers:
                loggers.remove(l)

        verbose_levels = logger.get_level_names()
        loggers_optmenus = {}
        row = 0
        for l in loggers:
            row += 1
            opt_menus = []
            label = tk.Label(new_window, text=f"{l.name}", font=("", 12, "bold"), justify="left")
            label.grid(row=row, column=0, sticky="w")
            for h in l.handlers:
                row += 1
                label = tk.Label(new_window, text=str(h))
                label.grid(row=row, column=0)

                selected_level = tk.StringVar(new_window)
                selected_level.set(logging.getLevelName(h.level))
                opt_menu = tk.OptionMenu(new_window, selected_level, *verbose_levels)
                opt_menu.grid(row=row, column=2)
                opt_menus.append(opt_menu)
            loggers_optmenus[l] = opt_menus

        cancel_button = tk.Button(new_window, text="Cancel", command=new_window.destroy)
        cancel_button.grid(row=row+1, column=1)

        apply_button = tk.Button(new_window, text="Apply", command=lambda: set_verbose_levels())
        apply_button.grid(row=row+1, column=2)

        def set_verbose_levels():
            for l, opt_menus in loggers_optmenus.items():
                for h, opt_menu in zip(l.handlers, opt_menus):
                    value = opt_menu.cget("text")
                    h.setLevel(value)
            new_window.destroy()

    def create_multidevice_frame(self, frame):
        self.multidevice_frame = tk.LabelFrame(frame, text="Multi-device control", font=("", 16), labelanchor="n", padx=10, pady=10, bd=4)
        self.multidevice_frame.pack(side="bottom", fill="both", expand=True)

        left_frame = tk.LabelFrame(self.multidevice_frame, text="Protocol settings", font=("", 12), labelanchor="n", padx=10, pady=10, bd=4)
        left_frame.pack(side="left", anchor="center")
        tk.Label(left_frame, text="Channel").grid(row=0, column=0)
        factor_label = tk.Label(left_frame, text="Factor")
        factor_label.grid(row=0, column=1)
        precision_label = tk.Label(left_frame, text="Prec(V)")
        precision_label.grid(row=0, column=2)
        ToolTip(factor_label, "Factor to convert the voltage setpoint to the\nactual voltage you want to remain within the step.\n"
                                        "For example, the cathode voltage is divided by\n0.286=80MOhm/(200+80)MOhm to get\nthe last ring voltage.")
        ToolTip(precision_label, "Precision (in volts) to consider that\nthe channel has reached the setpoint.")
        tk.Label(left_frame, text="vset (V)").grid(row=0, column=3)
        def option_changed(row_number, *args):
            channel = self.channel_optmenus[row_number].cget("text")
            if channel == "":
                # hide the vset entry
                self.vset_entries[row_number].grid_remove()
                self.factor_entries[row_number].grid_remove()
                self.precision_entries[row_number].grid_remove()
                # make the option menu as small as possible and blank
                self.channel_optmenus[row_number].config(width=1)
                self.channel_optmenus[row_number].grid(sticky="")
                self.channel_optmenus[row_number].config(text="")

            else:
                # show if hidden
                self.vset_entries[row_number].grid()
                self.factor_entries[row_number].grid()
                self.precision_entries[row_number].grid()
                # make the option menu as wide as the longest channel name
                self.channel_optmenus[row_number].config(width=len(max(self.all_channels.keys(), key=len)))
                # update the vset entry with the current value
                vset = self.channels_vset_guientries[channel].get()
                self.vset_entries[row_number].delete(0, tk.END)
                self.vset_entries[row_number].insert(0, str(vset))

        channel_options = list(self.all_channels.keys())
        channel_options.append("")
        n_rows = 0
        self.channel_optmenus = []
        self.vset_entries = []
        self.factor_entries = []
        self.precision_entries = []
        for i, ch_opt in enumerate(channel_options):
            ch_opt = channel_options[i]
            if ch_opt == "":
                continue
            n_rows += 1

            selected_option = tk.StringVar()
            selected_option.set(ch_opt)
            option_menu = tk.OptionMenu(left_frame, selected_option, *channel_options)
            option_menu.grid(row=i+1, column=0, sticky="ew", padx=5)
            self.channel_optmenus.append(option_menu)
            selected_option.trace("w", lambda *args, row_number=i: option_changed(row_number, *args))

            factor_entry = tk.Entry(left_frame, justify="center", width=5,
                                validate="key", validatecommand=self.validate_numeric_input)
            factor_entry.grid(row=i+1, column=1, padx=5)
            factor_entry.insert(0, "1" if ch_opt != "cathode" else "0.286") # 0.286 = 80MOhm/(200+80)MOhm to get last ring voltage (cathode voltage divider)
            self.factor_entries.append(factor_entry)

            precision_entry = tk.Entry(left_frame, justify="center", width=5,
                                validate="key", validatecommand=self.validate_numeric_input)
            precision_entry.grid(row=i+1, column=2, padx=5)
            precision_entry.insert(0, "1" if ch_opt != "cathode" else "50")
            self.precision_entries.append(precision_entry)

            vset_entry = tk.Entry(left_frame, justify="center", width=7,
                                validate="key", validatecommand=self.validate_numeric_input)
            vset_entry.grid(row=i+1, column=3, padx=5)
            vset_entry.insert(0, self.channels_vset_guientries[ch_opt].get())
            self.vset_entries.append(vset_entry)

        buttons_frame = tk.Frame(left_frame)
        buttons_frame.grid(row=n_rows+1, column=0, columnspan=3)

        tk.Label(buttons_frame, text="Step(V):").grid(row=0, column=0, sticky="E", padx=0)
        self.step_var = tk.StringVar()
        step_entry = tk.Entry(buttons_frame, justify="right", width=5, textvariable=self.step_var,
                                validate="key", validatecommand=self.validate_numeric_input)
        step_entry.grid(row=1, column=0, sticky="W", padx=0)
        step_entry.insert(0, "100")
        self.step_entry = step_entry

        apply_button = tk.Button(buttons_frame, text="Apply", command= lambda: self.raise_voltage_protocol_thread(self.step_var.get()))
        apply_button.grid(row=0, column=1, sticky="we", padx=5)

        turn_off_button = tk.Button(buttons_frame, text="Turn off", command= lambda: self.turn_off_protocol_thread(self.step_var.get()))
        turn_off_button.grid(row=1, column=1, sticky="we", padx=5)

        self.protocol_stop_button = tk.Button(buttons_frame, text="Stop", command= lambda: threading.Thread(target=self.stop_protocol).start(), fg="red4")
        self.protocol_stop_button.grid(row=0, column=2, rowspan=2, sticky="nsew")
        self.protocol_stop_button.grid_remove()
        self.protocol_settings_frame = left_frame

        right_frame = tk.Frame(self.multidevice_frame, padx=10, pady=10)
        right_frame.pack(side="right", anchor="center", padx=20)
        self.create_trip_recovery_frame(right_frame)
        all_devices_locks = tuple([gui.device_lock for gui in self.all_guis.values()])
        self.checksframe = ChecksFrame(right_frame, checks=self.checks, channels=self.all_channels, locks=all_devices_locks)
    def create_daq_frame(self, frame):
        daq_frame = tk.LabelFrame(frame, text="DAQ metrics", font=("", 16), labelanchor="n", padx=10, pady=10, bd=4)
        daq_frame.pack()

        tk.Label(daq_frame, text="Run number").grid(row=0, column=0, sticky="w")
        self.run_number_label = tk.Label(daq_frame, text="N/A")
        self.run_number_label.grid(row=0, column=1, sticky="e")

        tk.Label(daq_frame, text="Run type").grid(row=1, column=0, sticky="w")
        self.run_filename_label = tk.Label(daq_frame, text="N/A")
        self.run_filename_label.grid(row=1, column=1, sticky="e")

        tk.Label(daq_frame, text="Speed (MB/s)").grid(row=2, column=0, sticky="w")
        self.daq_speed_label = tk.Label(daq_frame, text="N/A")
        self.daq_speed_label.grid(row=2, column=1, sticky="e")

        tk.Label(daq_frame, text="Speed (events/s)").grid(row=3, column=0, sticky="w")
        self.daq_events_label = tk.Label(daq_frame, text="N/A")
        self.daq_events_label.grid(row=3, column=1, sticky="e")

        tk.Label(daq_frame, text="Number of events").grid(row=4, column=0, sticky="w")
        self.events_number_label = tk.Label(daq_frame, text="N/A")
        self.events_number_label.grid(row=4, column=1, sticky="e")

        self.auto_add_var = tk.IntVar()
        self.auto_add_var.set(0)
        self.last_run_number_from_google_sheet = None
        self.auto_add_var.trace("w", lambda *args : self.set_last_run_number_from_google_sheet())
        self.auto_add_to_googlesheet_checkbox = tk.Checkbutton(daq_frame, text="Auto add to Google Sheet", variable=self.auto_add_var)
        self.auto_add_to_googlesheet_checkbox.grid(row=5, column=0, columnspan=2, pady=10, sticky="nsew")

        self.add_to_googlesheet_button = tk.Button(daq_frame, text="Add to Google Sheet",
                                        command=self.add_run_to_googlesheet)
        self.add_to_googlesheet_button.grid(row=6, column=0, columnspan=2, pady=10, sticky="nsew")

        threading.Thread(target=self.daq_metrics_loop, daemon=True).start()

    def set_last_run_number_from_google_sheet(self, run_number=None):
        def get_last_run_number_from_google_sheet():
            self.last_run_number_from_google_sheet = utils.get_last_run_number_from_google_sheet()
        if run_number is None and self.last_run_number_from_google_sheet is None:
            threading.Thread(target=get_last_run_number_from_google_sheet).start()
        elif run_number is not None:
            self.last_run_number_from_google_sheet = run_number

    def daq_metrics_loop(self):
        self.metrics_fetcher = MetricsFetcherSSH(
                                url="http://localhost:8080/metrics",
                                hostname="192.168.3.80",
                                username="usertrex",
                                key_filename="/home/usertrex/.ssh/id_rsa"
                                )
        while True:
            self.metrics_fetcher.fetch_metrics()
            if self.metrics_fetcher.metrics:
                #output_filename = self.metrics_fetcher.get_filename()
                run_type = self.metrics_fetcher.get_filename_metadata().get("run_type", "N/A")
                self.run_number_label.config(text=f'{self.metrics_fetcher.get_metric("run_number"):.0f}')
                if self.metrics_fetcher.get_metric("run_number") != 0:
                    if self.add_to_googlesheet_thread and self.add_to_googlesheet_thread.is_alive():
                        pass
                    else:
                        self.add_to_googlesheet_button.config(state="normal")
                self.run_filename_label.config(text=run_type)
                self.daq_speed_label.config(text=f'{self.metrics_fetcher.get_metric("daq_speed_mb_per_sec_now"):.2f}')
                self.daq_events_label.config(text=f'{self.metrics_fetcher.get_metric("daq_speed_events_per_sec_now"):.1f}')
                self.events_number_label.config(text=f'{self.metrics_fetcher.get_metric("number_of_events"):,.0f}')
            else:
                self.run_number_label.config(text="N/A")
                self.daq_speed_label.config(text="N/A")
                self.daq_events_label.config(text="N/A")
                self.events_number_label.config(text="N/A")
                self.add_to_googlesheet_button.config(state="disabled")
            if (
                self.auto_add_var.get() == 1
                and self.run_number_label.cget("text") != "N/A"
                and self.last_run_number_from_google_sheet
                and int(self.last_run_number_from_google_sheet) < int(self.run_number_label.cget("text"))
            ):
                self.add_run_to_googlesheet()
            time.sleep(2.5)

    def add_run_to_googlesheet(self):
        def add_run():
            print("Adding run to Google Sheet...")
            self.add_to_googlesheet_button.config(state="disabled") # avoid spamming the button
            run_number = self.run_number_label.cget("text")
            self.set_last_run_number_from_google_sheet(int(run_number))
            start_date = time.strftime("%d/%m/%Y %H:%M")
            metadata = self.metrics_fetcher.get_filename_metadata()
            run_type = metadata.get("run_type", "")
            metadata.pop("run_type", None)
            metadata.pop("run_number", None)
            metadata.pop("Vm", None)
            metadata.pop("Vd", None)
            column_data = {ch: float(self.channels_vset_guilabel[ch].cget("text")) for ch in self.all_channels.keys()}
            column_data.update(metadata)
            column_data['threshold left'] = self.metrics_fetcher.get_total_threshold_for_fem_aget(2, 0)
            column_data['threshold right'] = self.metrics_fetcher.get_total_threshold_for_fem_aget(0, 0)
            column_data['multiplicity left'] = self.metrics_fetcher.get_total_multiplicity_for_fem_aget(2, 0)
            column_data['multiplicity right'] = self.metrics_fetcher.get_total_multiplicity_for_fem_aget(0, 0)
            row = utils.create_row_for_google_sheet(run_number, start_date, run_type, column_data)
            print(f"Row to be added: {row}")
            utils.append_row_to_google_sheet(row)
            self.add_to_googlesheet_button.config(state="normal")
            print("Run added to Google Sheet.")

        if self.add_to_googlesheet_thread and self.add_to_googlesheet_thread.is_alive():
            print("Run currently being added to Google Sheet. Please wait.")
            return
        self.add_to_googlesheet_thread = threading.Thread(target=add_run)
        self.add_to_googlesheet_thread.start()

    def create_trip_recovery_frame(self, frame):
        triprec_frame = tk.LabelFrame(frame, text="Trip recovery", font=("", 16), labelanchor="n", padx=10, pady=10, bd=4)
        triprec_frame.grid(row=0, column=0, sticky="nsew")

        upper_frame = tk.Frame(triprec_frame)
        upper_frame.grid(row=0, column=0, sticky="nsew")
        self.triprec_activate_button = tk.Button(upper_frame, text="Activate", command= lambda: self.triprec_active.set(True))
        self.triprec_activate_button.grid(row=1, column=0, pady=10, sticky="n")

        self.triprec_desactivate_button = tk.Button(upper_frame, text="Desactivate", command = lambda: self.triprec_active.set(False))
        self.triprec_desactivate_button.grid(row=1, column=1, pady=10, sticky="n")

        self.triprec_active = tk.BooleanVar(value=False)
        self.triprec_active.trace("w", self.trace_triprec_active)

        bottom_frame = tk.Frame(triprec_frame)
        bottom_frame.grid(row=1, column=0, sticky="nsew")
        triprec_cooldown_label = tk.Label(bottom_frame, text="Cooldown (min): ")
        triprec_cooldown_label.grid(row=2, column=0, columnspan=3, sticky="w")
        self.triprec_cooldown_entry = tk.Entry(bottom_frame, width=4, justify="right",
                                validate="key", validatecommand=self.validate_numeric_input)
        self.triprec_cooldown_entry.insert(0, "5")
        self.triprec_cooldown_entry.grid(row=2, column=3, sticky="w")

        tk.Label(bottom_frame, text="Trip count: ").grid(row=3, column=0, sticky="w")
        self.trip_count = tk.IntVar()
        self.trip_count.set(0)
        self.trip_count_label = tk.Label(bottom_frame, text="0")
        self.trip_count_label.grid(row=3, column=1, sticky="e")
        self.trip_count.trace("w", lambda *args: self.trip_count_label.config(text=str(self.trip_count.get())))
        tk.Label(bottom_frame, text=" / ").grid(row=3, column=2, sticky="ew", padx=0)
        self.max_count_entry = tk.Entry(bottom_frame, width=4, justify="right",
                                validate="key", validatecommand=self.validate_numeric_input)
        self.max_count_entry.insert(0, "3")
        self.max_count_entry.grid(row=3, column=3, sticky="w")

        self.triprec_logger = logging.getLogger("app.triprec")
        self.triprec_logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler(f"{logger.LOG_DIR}/trip_recovery.log")
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        file_handler.setLevel(logging.INFO)
        self.triprec_logger.addHandler(file_handler)

        #self.triprec_thread = threading.Thread(target=self.trip_recovery_loop, daemon=True).start()

    def trace_triprec_active(self, *args):
        def activate_trip_recovery():
            if self.triprec_thread and self.triprec_thread.is_alive():
                self.triprec_logger.debug("Trip recovery thread already running.")
                return
            # get the channels selected for trip recovery from the protocol settings frame
            self.triprec_channels = [ch.cget("text") for ch in self.channel_optmenus if ch.cget("text") != ""]
            # block the protocol settings frame
            enable_children(self.protocol_settings_frame, False)
            self.trip_count.set(0) # reset the trip counter
            self.triprec_logger.info("Trip recovery activated.")
            self.triprec_thread = threading.Thread(target=self.trip_recovery_loop, daemon=True)
            self.triprec_thread.start()
            self.triprec_activate_button.config(state="disabled")
            self.triprec_desactivate_button.config(state="normal")

        def desactivate_trip_recovery():
            self.triprec_desactivate_button.config(state="disabled") # first disable the button to avoid multiple threads
            # wait for the thread to finish due to the flag self.triprec_active being set to False
            if self.triprec_thread and self.triprec_thread.is_alive():
                self.triprec_thread.join() # this could block the main thread if it is not launched in a separate thread
            enable_children(self.protocol_settings_frame, True)
            self.triprec_channels = []
            self.triprec_logger.info("Trip recovery desactivated.")
            self.triprec_activate_button.config(state="normal")

        if self.triprec_active.get():
            activate_trip_recovery()
        else:
            threading.Thread(target=desactivate_trip_recovery).start()

    def trip_recovery_loop(self):
        while True:
            time.sleep(1)
            if not self.triprec_active.get():
                return # instead of break to avoid setting active to False again
            self.trip_detected = self.is_there_a_trip()
            if self.trip_detected:
                self.trip_count.set(self.trip_count.get() + 1)
                self.triprec_logger.info(
                    f"Trip number {str(self.trip_count.get())} detected: "
                    f"{self.caen_gui.alarm_detected}{self.caen_gui.ilk_detected}"
                )
                if self.trip_count.get() > int(self.max_count_entry.get()):
                    self.triprec_logger.error("Maximum trip count reached.")
                    break
                self.triprec_logger.debug("Starting trip recovery protocol.")
                try:
                    self.wait_for_channels_to_be_down(channels=self.triprec_channels, timeout=5*60, active_flag_attribute="triprec_active")
                except TimeoutError as e:
                    self.triprec_logger.critical(f"Error while waiting for channels to be down: {e}.")
                    break
                except KeyboardInterrupt as e:
                    self.triprec_logger.info(f"Error while waiting for channels to be down: {e}.")
                    return # instead of break to avoid setting active to False again

                self.clear_trip(channels=self.triprec_channels)
                sleep_time_minutes = 0
                if self.triprec_cooldown_entry:
                    sleep_time_minutes = float(self.triprec_cooldown_entry.get())
                if not self.sleep_time_with_escape(sleep_time_minutes*60, "triprec_active"):
                    return # instead of break to avoid setting active to False again
                self.turn_on_channels(channels=self.triprec_channels)
                self.spellman_gui.issue_command(self.spellman_gui.set_iset) # iset entry should be well adjusted manually

                protocol_finished_with_exceptions = False
                max_attempts = 10
                attempt = 0
                while self.triprec_active.get() and attempt < max_attempts:
                    attempt += 1
                    self.raise_voltage_protocol_thread(self.step_var.get())
                    try:
                        self.wait_for_raise_protocol_to_finish()
                        break
                    except (ValueError, NameError, AssertionError) as e:
                        self.triprec_logger.critical(f"Critical error while recovering trip: {e}.")
                        protocol_finished_with_exceptions = True
                        break
                    except (PermissionError, TimeoutError) as e:
                        self.triprec_logger.debug(f"Error while recovering trip: {e}. Attempt {attempt}/{max_attempts}.")
                        if self.is_there_a_trip():
                            protocol_finished_with_exceptions = True
                            break # restart the trip recovery protocol from the beginning because it tripped again
                        else:
                            self.turn_on_channels(channels=self.triprec_channels)
                            self.spellman_gui.issue_command(self.spellman_gui.set_iset) # iset entry should be well adjusted manually
                            continue
                    except KeyboardInterrupt as e:
                        self.triprec_logger.error(f"Error while recovering trip: {e}.")
                        protocol_finished_with_exceptions = True
                        break
                    except Exception as e:
                        self.triprec_logger.error(f"Unexpected error while recovering trip: {e}.")
                        protocol_finished_with_exceptions = True
                        break
                if protocol_finished_with_exceptions:
                    if attempt >= max_attempts:
                        self.triprec_logger.critical("Trip recovery failed. Maximum attempts reached.")
                    elif self.is_there_a_trip():
                        self.triprec_logger.debug("Trip recovery failed. Trip detected when raising voltage.")
                    else:
                        self.triprec_logger.critical("Trip recovery failed.")
                else:
                    self.triprec_logger.info("Trip recovery finished succesfully.")

        if self.triprec_active.get():
            self.triprec_active.set(False)


    def is_there_a_trip(self):
        if self.caen_gui.alarm_detected or self.caen_gui.ilk_detected:
            return True
    def clear_trip(self, channels=[]):
        # set vset of all channels to 0
        for ch, gui in self.channels_gui.items():
            if not ch in channels:
                continue
            channel = self.all_channels[ch]
            with gui.device_lock:
                channel.vset = 0

        self.caen_gui.issue_command(self.caen_gui.clear_alarm)
    def turn_on_channels(self, channels=[]):
        # turn on channels (and iset of spellman)
        for ch, gui in self.channels_gui.items():
            if not ch in channels:
                continue
            channel = self.all_channels[ch]
            with gui.device_lock:
                channel.turn_on()

    def wait_for_channels_to_be_down(self, channels=[], timeout=90, active_flag_attribute:str = ""):
        # check that the escape flag attribute is present in the object
        if active_flag_attribute and not hasattr(self, active_flag_attribute):
            raise AttributeError(f"Attribute {active_flag_attribute} not found")
        all_channels_down = False
        time_waiting = 0
        while not all_channels_down:
            all_channels_down = True
            for ch, vmon_label in self.channels_vmon_guilabel.items():
                if not ch in channels:
                    continue
                vmon = float(vmon_label.cget("text"))
                if ch == "cathode": # TODO: add precision for each channel here to avoid special cases
                    if vmon<50:
                        continue
                if vmon > 5.0:
                    all_channels_down = False
                    break
            time.sleep(1)
            time_waiting += 1
            if time_waiting > timeout:
                raise TimeoutError("Timeout waiting for channels to be down")
                break
            active_flag_value = getattr(self, active_flag_attribute) if active_flag_attribute else True
            if isinstance(active_flag_value, tk.Variable):
                active_flag_value = active_flag_value.get()
            if not active_flag_value:
                raise KeyboardInterrupt(f"'wait_for_channels_to_be_down' manually stopped due to {active_flag_attribute}")
                break

    def wait_for_raise_protocol_to_finish(self, active_flag_attribute:str = ""):
        # check that the escape flag attribute is present in the object
        if active_flag_attribute and not hasattr(self, active_flag_attribute):
            raise AttributeError(f"Attribute {active_flag_attribute} not found")
        if self.protocol_thread:
            while self.protocol_thread.is_alive():
                time.sleep(0.1)
                active_flag_value = getattr(self, active_flag_attribute) if active_flag_attribute else True
                if isinstance(active_flag_value, tk.Variable):
                    active_flag_value = active_flag_value.get()
                if not active_flag_value:
                    raise KeyboardInterrupt(f"Protocol manually stopped due to {active_flag_attribute}")
        if self.protocol_thread.exception:
            raise self.protocol_thread.exception

    def sleep_time_with_escape(self, sleep_time_seconds, active_flag_attribute:str = ""):
        # check that the escape flag attribute is present in the object
        if active_flag_attribute and not hasattr(self, active_flag_attribute):
            raise AttributeError(f"Attribute {active_flag_attribute} not found")
        # sleep for sleep_time seconds, checking every second if the escape flag is set
        # does not check the escape flag if it is not given
        for _ in range(int(sleep_time_seconds)):
            time.sleep(1)
            active_flag_value = getattr(self, active_flag_attribute) if active_flag_attribute else True
            if isinstance(active_flag_value, tk.Variable):
                active_flag_value = active_flag_value.get()
            if not active_flag_value:
                return False
        return True

    def stop_protocol(self):
        self.protocol_stop_flag = True
        print("Stopping protocol...")
        if self.protocol_thread and self.protocol_thread.is_alive():
            self.protocol_thread.join() # this will block the main thread until the protocol thread finishes
        print("Protocol stopped.")

    def protocol_cleanup(self):
        if self.step_entry:
            # avoid enabling it if the whole frame is disabled (use channel_optmenus to check)
            if self.channel_optmenus and self.channel_optmenus[0].cget("state") == "normal":
                self.step_entry.config(state="normal")
        if self.protocol_stop_button:
            self.protocol_stop_button.grid_remove()
        self.protocol_stop_flag = False

    def toggle_scrolled_text(self):
        # Toggle the visibility of the ScrolledText widget
        if self.text_visible:
            self.scrolled_text.pack_forget()  # Hide the widget
            self.toggle_button.config(text="\u25BC Show terminal output")
        else:
            self.scrolled_text.pack(side="bottom", fill="both", expand=False, padx=5)
            self.toggle_button.config(text="\u25B2 Hide terminal output")

        self.text_visible = not self.text_visible

    def reset_logging(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def redirect_logging(self, widget):
        logger = PrintToTextWidget(widget)
        sys.stdout = logger
        sys.stderr = logger

    def raise_voltage_protocol_thread(self, step = 100):
        try:
            step_number = float(step)
        except ValueError:
            print("Invalid step value")
            self.step_var.set("100")
            return
        if step_number <= 0 or step_number > 100:
            print("Step value must be between 0 and 100")
            self.step_var.set("100")
            return

        if self.protocol_stop_button:
            self.protocol_stop_button.grid()

        if self.protocol_thread and self.protocol_thread.is_alive():
            print("Protocol thread already running")
            return
        self.protocol_thread = utils.ExceptionThread(target=self.raise_voltage_protocol, args=(step_number,))
        self.protocol_thread.start()

    def turn_off_protocol_thread(self, step = 100):
        try:
            step_number = float(step)
        except ValueError:
            print("Invalid step value")
            self.step_var.set("100")
            return
        if step_number <= 0 or step_number > 100:
            print("Step value must be between 0 and 100")
            self.step_var.set("100")
            return

        if self.protocol_stop_button:
            self.protocol_stop_button.grid()

        if self.protocol_thread and self.protocol_thread.is_alive():
            print("Protocol thread already running")
            return
        self.protocol_thread = threading.Thread(target=self.turn_off_protocol, args=(step_number,))
        self.protocol_thread.start()

    def raise_voltage_protocol(self, step = 100, timeout = 60):
        # final_vset = {'cathode' : 2000, 'gem top' : 600, 'gem bottom' : 350, 'mesh left' : 250}
        def get_vmon(ch_name):
            label = self.channels_vmon_guilabel[ch_name]
            vmon = -1
            if label is not None:
                if "cget" in dir(label):
                    vmon = float(label.cget("text"))
                else:
                    vmon = float(label.get())
            else:
                with self.channels_gui[ch_name].device_lock:
                    vmon = self.all_channels[ch_name].vmon
            return vmon
        def have_all_channels_reached(vset, precision):
            for ch, v in vset.items():
                vmon = get_vmon(ch)
                prec = precision.get(ch, 1)
                if v - vmon > prec:
                    return False
            return True
        
        def are_all_channels_vset_above(vsets):
            for ch, v in vsets.items():
                vset = float(self.channels_vset_guilabel[ch].cget("text"))
                if vset < v:
                    return False
            return True

        final_vset = {}
        factors = {}
        precision = {}
        for i, ch in enumerate(self.channel_optmenus):
            if ch.cget("text") == "":
                continue
            val = self.vset_entries[i].get()
            try:
                val = float(val)
            except ValueError:
                continue
            final_vset[ch.cget("text")] = float(self.vset_entries[i].get())
            factors[ch.cget("text")] = float(self.factor_entries[i].get())
            precision[ch.cget("text")] = float(self.precision_entries[i].get())
        
        if len(final_vset) < 1: # makes no sense to use this with less than 2 channels
            print("No valid voltage setpoints found")
            self.protocol_cleanup()
            raise ValueError("No valid voltage setpoints found")
            return

        # check that all channels involved are on
        for ch in final_vset.keys():
            if ch not in self.all_channels.keys():
                print(f"Channel {ch} not found in the list of available channels")
                self.protocol_cleanup()
                raise NameError(f"Channel {ch} not found in the list of available channels")
                return
            with self.channels_gui[ch].device_lock:
                if not self.all_channels[ch].on:
                    #print(f"Channel {ch} is off. Turn it on before running the protocol")
                    self.protocol_cleanup()
                    raise PermissionError(f"Channel {ch} is off. Turn it on before running the protocol")
                    return

        if self.step_entry:
            self.step_entry.config(state="disabled")

        temp_vset = {k: 0 for k in final_vset.keys()} # initialize the temporary voltage setpoints

        max_vset = max([round(v*f) for v, f in zip(final_vset.values(), factors.values())])
        n_steps = int( max_vset / step ) + 1
        print(f"Number of steps: {n_steps}")
        vset = 0
        for _ in range(n_steps):
            if self.protocol_stop_flag:
                break
            vset = vset + step
            temp_vset = {k: round(vset/f) for k, f in zip(final_vset.keys(), factors.values())}
            for ch, f in final_vset.items():
                temp_vset[ch] = f if temp_vset[ch] >= f else temp_vset[ch]
            if (are_all_channels_vset_above(temp_vset)
                and have_all_channels_reached(temp_vset, precision)
            ):
                continue
            print(f"Step {_+1}: {temp_vset}")

            # simulate the checks results before applying the new vsets
            parameters_values = {}
            for ch, v in temp_vset.items():
                parameters_values[ch.replace(" ", "") + ".vset"] = v
            # multidevice checks
            if not self.checksframe.simulate_check_conditions(parameters_values):
                print("Step did not pass the multidevice checks.")
                self.protocol_cleanup()
                raise AssertionError("Step did not pass the multidevice checks.")
                return
            # individual device checks
            for device, gui in self.all_guis.items():
                try:
                    if not gui.checksframe.simulate_check_conditions(parameters_values):
                        print(f"Step did not pass the {device} checks.")
                        self.protocol_cleanup()
                        raise AssertionError(f"Step did not pass the {device} checks.")
                        return
                except AttributeError:
                    pass

            if self.protocol_stop_flag:
                break
            # apply vsets to the channels
            for ch, v in temp_vset.items():
                if get_vmon(ch) > v:
                    #print(f"Voltage monitor for channel {ch} is higher than the setpoint. Skipping the step.")
                    continue
                # change the vset entry to the new value (emulate the human manually changing the value)
                self.channels_vset_guientries[ch].delete(0, tk.END)
                self.channels_vset_guientries[ch].insert(0, str(v))
                channel = self.all_channels[ch]
                try:
                    self.channels_gui[ch].issue_command(channel.vset(v))
                except (AttributeError, TypeError): # for the simulators
                    channel.vset = v
                except Exception as e:
                    print(f"Error setting voltage for channel {ch}: {e}")
                    self.protocol_cleanup()
                    raise SystemError(f"Error setting voltage for channel {ch}: {e}")
                    return
                # self.all_channels[ch].vset = v
            
            # wait for the channels to reach the setpoints
            all_channels_reached = False
            time_waiting = 0
            while not all_channels_reached:
                if self.protocol_stop_flag:
                    break
                all_channels_reached = have_all_channels_reached(temp_vset, precision)
                time.sleep(1) # wait 1 second before next check
                time_waiting += 1 # use same time as the number of seconds waited
                if time_waiting > timeout:
                    print("Timeout waiting for channels to reach the setpoints. Stopping protocol.")
                    self.protocol_stop_flag = True
                    self.protocol_cleanup()
                    raise TimeoutError("Timeout waiting for channels to reach the setpoints.")
            if self.protocol_stop_flag:
                break
            time.sleep(2) # wait 3 seconds before next step

        self.protocol_cleanup()

    def turn_off_protocol(self, step=100, timeout=60):
        def get_vmon(ch_name):
            label = self.channels_vmon_guilabel[ch_name]
            vmon = -1
            if label is not None:
                if "cget" in dir(label):
                    vmon = float(label.cget("text"))
                else:
                    vmon = float(label.get())
            else:
                with self.channels_gui[ch_name].device_lock:
                    vmon = self.all_channels[ch_name].vmon
            return vmon

        current_vset = {}
        factors = {}
        precision = {}
        for i, ch in enumerate(self.channel_optmenus):
            if ch.cget("text") == "":
                continue
            current_vset[ch.cget("text")] = float(self.channels_vset_guientries[ch.cget("text")].get())
            factors[ch.cget("text")] = float(self.factor_entries[i].get())
            precision[ch.cget("text")] = float(self.precision_entries[i].get())
        
        if len(current_vset) < 1: # makes no sense to use this with less than 2 channels
            print("No valid voltage setpoints found")
            self.protocol_cleanup()
            return
        
        # check that all channels involved are on
        for ch in current_vset.keys():
            if ch not in self.all_channels.keys():
                print(f"Channel {ch} not found in the list of available channels")
                self.protocol_cleanup()
                return
            with self.channels_gui[ch].device_lock:
                if not self.all_channels[ch].on:
                    print(f"WARNING: Channel {ch} is already off.")
        
        if self.step_entry:
            self.step_entry.config(state="disabled")

        temp_vset = current_vset # initialize the temporary voltage setpoints

        max_vset = max([round(v*f) for v, f in zip(current_vset.values(), factors.values())])
        n_steps = int( max_vset / step ) + 1
        print(f"Number of steps: {n_steps}")
        channels_reached = 0
        for _ in range(n_steps):
            if self.protocol_stop_flag:
                break
            temp_vset = {k: round(t-step/f) for k, t, f in zip(current_vset.keys(), temp_vset.values(), factors.values())}
            if any([t <= 0 for t in temp_vset.values()]):
                channels_reached += 1
            for ch in temp_vset.keys():
                temp_vset[ch] = 0 if temp_vset[ch] <= 0 else temp_vset[ch]
            print(f"Step {_+1}: {temp_vset}")

            # simulate the checks results before applying the new vsets
            parameters_values = {}
            for ch, v in temp_vset.items():
                parameters_values[ch.replace(" ", "") + ".vset"] = v
            # multidevice checks
            if not self.checksframe.simulate_check_conditions(parameters_values):
                print("Step did not pass the multidevice checks.")
                self.protocol_cleanup()
                return
            # individual device checks
            for device, gui in self.all_guis.items():
                try:
                    if not gui.checksframe.simulate_check_conditions(parameters_values):
                        print(f"Step did not pass the {device} checks.")
                        self.protocol_cleanup()
                        return
                except AttributeError:
                    pass

            if self.protocol_stop_flag:
                break
            # apply vsets to the channels
            for ch, v in temp_vset.items():
                if get_vmon(ch) < v:
                    # print(f"Voltage monitor for channel {ch} is lower than the setpoint. Skipping the step.")
                    continue
                # change the vset entry to the new value (emulate the human manually changing the value)
                self.channels_vset_guientries[ch].delete(0, tk.END)
                self.channels_vset_guientries[ch].insert(0, str(v))
                channel = self.all_channels[ch]
                try:
                    self.channels_gui[ch].issue_command(channel.vset(v))
                except (AttributeError, TypeError):
                    channel.vset = v
                except Exception as e:
                    print(f"Error setting voltage for channel {ch}: {e}")
                    self.protocol_cleanup()
                    return
                # self.all_channels[ch].vset = v

            # wait for the channels to reach the setpoints
            all_channels_reached = False
            time_waiting = 0
            while not all_channels_reached:
                if self.protocol_stop_flag:
                    break
                all_channels_reached = True
                for ch in temp_vset.keys():
                    vmon = get_vmon(ch)
                    prec = precision.get(ch, 1)
                    if vmon - temp_vset[ch] > prec:
                        all_channels_reached = False
                        break
                time.sleep(1) # wait 1 second before next check
                time_waiting += 1
                if time_waiting > timeout:
                    print("Timeout waiting for channels to reach the setpoints. Stopping protocol.")
                    self.protocol_stop_flag = True

            time.sleep(2) # wait seconds before next step

        # turn off the channels
        if not self.protocol_stop_flag:
            for ch in temp_vset.keys():
                with self.channels_gui[ch].device_lock:
                    self.all_channels[ch].turn_off()

        self.protocol_cleanup()


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Enable test mode")
    parser.add_argument("--port", type=str, help="Select port", default="/dev/ttyUSB0")
    parser.add_argument("--checks", type=str, help="Select checks configuration file", default="checks_config.toml")

    args = parser.parse_args()

    checks_caen = load_checks_from_toml_file(args.checks, "caen")
    checks_spellman = load_checks_from_toml_file(args.checks, "spellman")
    checks_multidevice = load_checks_from_toml_file(args.checks, "multidevice")

    if not args.test:
        with hvps.Caen(port=args.port) as caen:
            print("port:", caen.port)
            print("baudrate:", caen.baudrate)
            m = caen.module(0)
            spellman = spll.Spellman()
            app = HVGUI(caen_module=m, spellman_module=spellman, checks_caen=checks_caen, checks_spellman=checks_spellman, checks_multidevice=checks_multidevice)

    else:
        from simulators import ModuleSimulator, SpellmanSimulator
        caen_module = ModuleSimulator(4, trip_probability=0)
        spellman_module = SpellmanSimulator()
        app = HVGUI(caen_module=caen_module, spellman_module=spellman_module, checks_caen=checks_caen, checks_spellman=checks_spellman, checks_multidevice=checks_multidevice, log=False)


