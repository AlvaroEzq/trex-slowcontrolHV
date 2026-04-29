from __future__ import annotations

import logging
import threading
import threading
import tkinter as tk
import argparse
import datetime
import time

import utils
from daqmetrics import MetricsFetcher, MetricsFetcherSSH, FeminosDaqMetrics, FemDaqMetrics
from utilsgui import ToolTip
from devicegui import DeviceGUI

class DaqMetricsGUI(DeviceGUI):
    """
    GUI for monitoring DAQ metrics, such as run number, run type, run duration, and DAQ speed. It fetches the metrics using a MetricsFetcher instance and updates the GUI accordingly. The GUI also provides buttons to add the metrics to a Google Sheet.
    """

    def __init__(self, daqmetrics, all_channels=None, channels_vset_guilabel=None, parent_frame=None):

        self.daqmetrics = daqmetrics
        self.all_channels = all_channels if all_channels is not None else {} # list of all channels of the main GUI
        self.channels_vset_guilabel = channels_vset_guilabel if channels_vset_guilabel is not None else {} # list of all channels vset guilabels of the main GUI, to be able to fetch the vset values when adding to google sheet
        self.run_number_label = None
        self.run_tag_label = None
        self.run_endtime_label = None
        self.daq_speed_label = None
        self.daq_events_label = None
        self.events_number_label = None
        self.add_to_googlesheet_button = None
        self.add_to_googlesheet_thread = None
        self.auto_add_var = None
        self.check_entries_var = None
        self.number_of_entries = None
        self.datetime_last_entries_change = None
        self.alarm_level_sent = logging.NOTSET

        super().__init__(
                        device=daqmetrics,
                        channels_name=[],
                        parent_frame=parent_frame,
                        logging_enabled=False,
                        read_loop_time=60,
                        )
    
    def create_gui(self):
        self.main_frame = tk.LabelFrame(self.root, text=f"{self.daqmetrics.name}", font=("", 16), padx=10, pady=10, labelanchor="n", bd=4)
        self.main_frame.pack(expand=False)
        self.main_frame = self.create_main_frame(self.main_frame, self.channels_name)
    
    def create_main_frame(self, frame, channels_name):
        
        daq_frame = tk.Frame(frame, padx=0, pady=0, bd=0, highlightthickness=0)
        daq_frame.pack()

        tk.Label(daq_frame, text="Run number").grid(row=0, column=0, sticky="w")
        self.run_number_label = tk.Label(daq_frame, text="N/A")
        self.run_number_label.grid(row=0, column=1, sticky="e")

        tk.Label(daq_frame, text="Run tag").grid(row=1, column=0, sticky="w")
        self.run_tag_label = tk.Label(daq_frame, text="N/A")
        self.run_tag_label.grid(row=1, column=1, sticky="e")
        
        tk.Label(daq_frame, text="Start time").grid(row=2, column=0, sticky="w")
        self.run_starttime_label = tk.Label(daq_frame, text="N/A")
        self.run_starttime_label.grid(row=2, column=1, sticky="e")

        tk.Label(daq_frame, text="End time").grid(row=3, column=0, sticky="w")
        self.run_endtime_label = tk.Label(daq_frame, text="N/A")
        self.run_endtime_label.grid(row=3, column=1, sticky="e")

        tk.Label(daq_frame, text="Subrun number").grid(row=4, column=0, sticky="w")
        self.subrun_number_label = tk.Label(daq_frame, text="N/A")
        self.subrun_number_label.grid(row=4, column=1, sticky="e")

        tk.Label(daq_frame, text="Speed (events/s)").grid(row=5, column=0, sticky="w")
        self.daq_events_label = tk.Label(daq_frame, text="N/A")
        self.daq_events_label.grid(row=5, column=1, sticky="e")

        tk.Label(daq_frame, text="Number of events").grid(row=6, column=0, sticky="w")
        self.events_number_label = tk.Label(daq_frame, text="N/A")
        self.events_number_label.grid(row=6, column=1, sticky="e")

        self.check_entries_var = tk.IntVar()
        self.check_entries_var.set(0)
        self.check_entries_change_checkbox = tk.Checkbutton(daq_frame, text="Check entries (TCM)", variable=self.check_entries_var, selectcolor="gray")
        self.check_entries_var.set(1) # enable by default
        self.check_entries_change_checkbox.grid(row=7, column=0, columnspan=2, pady=5, sticky="nsew")

        self.auto_add_var = tk.IntVar()
        self.auto_add_var.set(0)
        self.last_run_number_from_google_sheet = None
        self.auto_add_var.trace_add("write", lambda *args : self.set_last_run_number_from_google_sheet())
        self.auto_add_var.set(1)
        self.auto_add_to_googlesheet_checkbox = tk.Checkbutton(daq_frame, text="Auto add to Google Sheet", variable=self.auto_add_var, selectcolor="gray")
        self.auto_add_to_googlesheet_checkbox.grid(row=8, column=0, columnspan=2, pady=0, sticky="nsew")


        self.add_to_googlesheet_button = tk.Button(daq_frame, text="Add to Google Sheet",
                                        command=self.add_run_to_googlesheet)
        self.add_to_googlesheet_button.grid(row=9, column=0, columnspan=2, pady=10, sticky="nsew")

        #threading.Thread(target=self.daq_metrics_loop, daemon=True).start()
    
    def set_last_run_number_from_google_sheet(self, run_number=None):
        def get_last_run_number_from_google_sheet():
            self.last_run_number_from_google_sheet = utils.get_last_run_number_from_google_sheet()
        if run_number is None and self.last_run_number_from_google_sheet is None:
            threading.Thread(target=get_last_run_number_from_google_sheet).start()
        elif run_number is not None:
            self.last_run_number_from_google_sheet = run_number

    def add_run_to_googlesheet(self):
        def add_run():
            print("Adding run to Google Sheet...")
            self.add_to_googlesheet_button.config(state="disabled") # avoid spamming the button
            run_number = self.run_number_label.cget("text")
            self.set_last_run_number_from_google_sheet(int(run_number))
            start_date = ""
            try:
                start_date = self.daqmetrics.get_run_file_time_string()
            except:
                start_date = time.strftime("%d/%m/%Y %H:%M")
            metadata = self.daqmetrics.get_all_metadata()
            run_tag = metadata.get("run_tag", "")
            metadata.pop("run_tag", None)
            metadata.pop("run_number", None)
            metadata.pop("Vm", None)
            metadata.pop("Vd", None)
            column_data = {ch: float(self.channels_vset_guilabel[ch].cget("text")) for ch in self.all_channels.keys()}
            column_data.update(metadata)
            column_data['threshold left'] = self.daqmetrics.get_total_threshold_for_fem_aget(2, 0)
            column_data['threshold right'] = self.daqmetrics.get_total_threshold_for_fem_aget(0, 0)
            column_data['multiplicity left'] = self.daqmetrics.get_total_multiplicity_for_fem_aget(2, 0)
            column_data['multiplicity right'] = self.daqmetrics.get_total_multiplicity_for_fem_aget(0, 0)
            row = utils.create_row_for_google_sheet(run_number, start_date, run_tag, column_data)
            print(f"Row to be added: {row}")
            utils.append_row_to_google_sheet(row)
            self.add_to_googlesheet_button.config(state="normal")
            print("Run added to Google Sheet.")

        if self.add_to_googlesheet_thread and self.add_to_googlesheet_thread.is_alive():
            print("Run currently being added to Google Sheet. Please wait.")
            return
        self.add_to_googlesheet_thread = threading.Thread(target=add_run)
        self.add_to_googlesheet_thread.start()

    def read_values(self):

        self.daqmetrics.fetch_everything()
        if self.daqmetrics.fetcher.metrics:
            #output_filename = self.daqmetrics.get_filename()
            run_tag = self.daqmetrics.get_run_tag()
            self.run_number_label.config(text=f'{self.daqmetrics.get_run_number():.0f}')
            if self.daqmetrics.get_metric("run_number") != 0:
                if self.add_to_googlesheet_thread and self.add_to_googlesheet_thread.is_alive():
                    pass
                else:
                    self.add_to_googlesheet_button.config(state="normal")
            self.run_tag_label.config(text=run_tag if run_tag else "")
            run_duration = self.daqmetrics.get_run_time_seconds()
            run_start = self.daqmetrics.get_run_start_time()
            if run_start is not None:
                self.run_starttime_label.config(text=f'{run_start.strftime("%d/%m/%Y %H:%M")}')
                endtime = run_start + datetime.timedelta(seconds=run_duration)
                self.run_endtime_label.config(text=f'{endtime.strftime("%d/%m/%Y %H:%M")}')
            else:
                endtime = None
                self.run_starttime_label.config(text=f'')
                self.run_endtime_label.config(text=f'')
                
            self.daq_events_label.config(text=f'{self.daqmetrics.get_rate():.2f}')
            number_of_events = self.daqmetrics.get_number_of_events()
            self.events_number_label.config(text=f'{number_of_events:,.0f}')

            # Checking if the number of entries is changing is done as an indirect way to check if the TCM is running fine
            if self.check_entries_var.get() == 1:
                if self.number_of_entries is None or number_of_events != self.number_of_entries:
                    self.number_of_entries = number_of_events
                    self.datetime_last_entries_change = datetime.datetime.now()
                    self.alarm_level_sent = logging.NOTSET # reset alarm level sent
                else:
                    time_diff = datetime.datetime.now() - self.datetime_last_entries_change
                    if time_diff.total_seconds() > 3600*24: # 24 hours without new entries
                        # Send alarm only if lower level was sent
                        if self.alarm_level_sent < logging.CRITICAL:
                            self.logger.critical("No new entries in the DAQ for more than 24 hours! Check TCM state...")
                            self.alarm_level_sent = logging.CRITICAL
                    elif time_diff.total_seconds() > 3600*10: # 10 hours without new entries
                        if self.alarm_level_sent < logging.ERROR:
                            self.logger.error("No new entries in the DAQ for more than 10 hours. Check TCM state...")
                            self.alarm_level_sent = logging.ERROR
                    elif time_diff.total_seconds() > 3600: # 1 hour without new entries
                        if self.alarm_level_sent < logging.WARNING:
                            self.logger.warning("No new entries in the DAQ for more than 1 hour. Check TCM state...")
                            self.alarm_level_sent = logging.WARNING
            else:
                # reset
                self.number_of_entries = None
                self.datetime_last_entries_change = None
                self.alarm_level_sent = logging.NOTSET
            
            # Check for background runs that have finished or will finish soon
            if any(b in run_tag.lower() for b in ["background", "bg", "bckg", "bkg"]):
                if run_duration < 24*3600: # to catch when run is launched without changing the calibration LOOP time
                    self.run_endtime_label.config(fg="red")
                else:
                    self.run_endtime_label.config(fg="black") # TODO: better to go back to default color

                if endtime and endtime < datetime.datetime.now(): # catch if run has finished
                    self.logger.error(f"Background run {int(self.daqmetrics.get_metric('run_number'))} has finished!")

            subrun_number = self.daqmetrics.get_subrun_number()
            self.subrun_number_label.config(text=f'{subrun_number}')
        else:
            self.run_number_label.config(text="N/A")
            self.run_tag_label.config(text="N/A")
            self.run_starttime_label.config(text="N/A")
            self.run_endtime_label.config(text="N/A")
            self.daq_events_label.config(text="N/A")
            self.events_number_label.config(text="N/A")
            self.subrun_number_label.config(text="N/A")
            self.add_to_googlesheet_button.config(state="disabled")
            # don't reset here the number of entries and datetime_last_entries_change, just in case the metrics server is down for a while
        if (
            self.auto_add_var.get() == 1
            and self.run_number_label.cget("text") != "N/A"
            and self.last_run_number_from_google_sheet
            and int(self.last_run_number_from_google_sheet) < int(self.run_number_label.cget("text"))
        ):
            self.add_run_to_googlesheet()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daq metrics GUI")
    args = parser.parse_args()

    #metrics_fetcher = MetricsFetcher(url="http://localhost:8080/metrics")
    metrics_fetcher = MetricsFetcherSSH(url="http://localhost:8080/metrics",hostname="192.168.3.80",username="usertrex",key_filename="/home/usertrex/.ssh/id_rsa")
    
    #daqmetrics = FeminosDaqMetrics(metrics_fetcher)
    daqmetrics = FemDaqMetrics(metrics_fetcher)
    
    DaqMetricsGUI(daqmetrics)