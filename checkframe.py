import tkinter as tk
from tkinter import messagebox
import threading
import time

from check import Check, MultiDeviceCheck
from tooltip import ToolTip

class ChecksFrame:
    def __init__(self, parent_frame = None, checks = None, all_channels = None, all_locks = None):
        if checks is None:
            checks = []
        if all_channels is None:
            all_channels = {}
        if all_locks is None:
            all_locks = {}

        self.root = parent_frame
        self.checks = checks
        self.all_channels = all_channels
        self.all_locks = all_locks

        self.checks_vars = []
        self.checks_checkboxes = []
        self.checks_tooltips = []
        self.edit_checks_button = None

        self.create_security_frame()

    def set_checks(self, checks : list):
        if checks is None:
            checks = []
        self.checks = checks
        self.set_checks_channels_and_locks()

    def create_security_frame(self):
        start_mainloop = False
        if self.root is None:
            self.root = tk.Tk()
            self.root.title("Security checks")
            start_mainloop = True

        security_frame = tk.LabelFrame(self.root, text="Security checks")
        security_frame.grid(row=2, column=0, padx=10, pady=10, sticky="NWE")

        self.set_checks_channels_and_locks()

        self.checks_vars = []
        self.checks_checkboxes = []
        self.checks_tooltips = []
        for i, check in enumerate(self.checks):
            var = tk.BooleanVar()
            var.set(True)
            self.checks_vars.append(var)
            var.trace_variable("w", lambda *args, x=i: self.checks[x].set_active(self.checks_vars[x].get()))

            checkbox = tk.Checkbutton(
                security_frame,
                text=f" {check.name}",
                variable=var,
                font=("", 12),
                borderwidth=0,
                highlightthickness=0,
            )
            checkbox.grid(row=i+1, column=0, sticky="w", padx=0, pady=0)
            self.checks_checkboxes.append(checkbox)
            tooltip = ToolTip(checkbox, check.description + "( " + check.condition + " )")
            self.checks_tooltips.append(tooltip)
        
        self.edit_checks_button = tk.Button(
            security_frame,
            text="Edit checks",
            font=("Arial", 10),
            command=self.open_edit_checks_window,
        )
        self.edit_checks_button.grid(row=len(self.checks)+1, column=0, padx=10, pady=10, sticky="w")

        self.frame = security_frame
        self.start_background_threads()

        if start_mainloop:
            self.root.mainloop()

        return security_frame

    def open_edit_checks_window(self):
        new_window = tk.Toplevel(self.root)
        new_window.title("Edit checks")
        new_window.configure(bg="darkblue")

        tk.Label(new_window, text="Check name", font=("Arial", 12), bg="blue", fg="white").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        tk.Label(new_window, text="Condition", font=("Arial", 12), bg="blue", fg="white").grid(row=0, column=1, padx=10, pady=5, sticky="w")
        tk.Label(new_window, text="Description", font=("Arial", 12), bg="blue", fg="white").grid(row=0, column=2, padx=10, pady=5, sticky="w")

        name_entries = []
        condition_entries = []
        description_entries = []
        delete_buttons = []
        for i, check in enumerate(self.checks):
            name_entry = tk.Entry(new_window, width=20, justify="center")
            name_entry.insert(0, check.name)
            name_entry.grid(row=i+1, column=0, padx=10, pady=5)
            name_entries.append(name_entry)

            condition_entry = tk.Entry(new_window, width=40, justify="center")
            condition_entry.insert(0, check.condition)
            condition_entry.grid(row=i+1, column=1, padx=10, pady=5)
            condition_entries.append(condition_entry)

            description_entry = tk.Entry(new_window, width=50, justify="center")
            description_entry.insert(0, check.description)
            description_entry.grid(row=i+1, column=2, padx=10, pady=5)
            description_entries.append(description_entry)
            
        def apply_changes():
            for i, check in enumerate(self.checks):
                name = name_entries[i].get()
                condition = condition_entries[i].get()
                description = description_entries[i].get()
                channels = self.all_channels.copy() # set all the channels for the checks
                self.checks[i] = Check(name, condition, channels, description)
                self.checks_checkboxes[i].config(text=f" {name}")
                self.checks_tooltips[i].change_text(description)
            new_window.destroy()

        def add_check():
            name_entries.append(tk.Entry(new_window, width=20, justify="center"))
            name_entries[-1].grid(row=len(name_entries), column=0, padx=10, pady=5)
            condition_entries.append(tk.Entry(new_window, width=40, justify="center"))
            condition_entries[-1].grid(row=len(condition_entries), column=1, padx=10, pady=5)
            description_entries.append(tk.Entry(new_window, width=50, justify="center"))
            description_entries[-1].grid(row=len(description_entries), column=2, padx=10, pady=5)
            # move the buttons to the bottom
            new_check_button.grid(row=len(name_entries)+1, column=0, padx=10, pady=10, sticky="w")
            cancel_button.grid(row=len(name_entries)+2, column=0, padx=10, pady=10, sticky="e")
            apply_button.grid(row=len(name_entries)+2, column=1, padx=10, pady=10, sticky="w")
            # add the check to the list
            self.checks_vars.append(tk.BooleanVar())
            self.checks_vars[-1].set(True)
            self.checks_vars[-1].trace_variable("w", lambda *args, x=len(self.checks)-1: self.checks[x].set_active(self.checks_vars[x].get()))
            self.checks_checkboxes.append(tk.Checkbutton(
                self.frame,
                text=f"",
                variable=self.checks_vars[-1],
                font=("", 12),
                borderwidth=0,
                highlightthickness=0,
            ))
            self.checks_checkboxes[-1].grid(row=len(self.checks)+1, column=0, sticky="w", padx=0, pady=0)
            self.checks.append(MultiDeviceCheck("", ""))
            self.set_checks_channels_and_locks()
            self.checks_tooltips.append(ToolTip(self.checks_checkboxes[-1], self.checks[-1].description + "( " + self.checks[-1].condition + " )"))
            # move the edit button to the bottom
            self.edit_checks_button.grid(row=len(self.checks)+1, column=0, padx=10, pady=10, sticky="w")

        # Add "add check" button
        new_check_button = tk.Button(
            new_window,
            text="Add check",
            font=("Arial", 10),
            bg="navy",
            fg="white",
            command=add_check,
        )
        new_check_button.grid(row=len(self.checks)+1, column=0, padx=10, pady=10, sticky="w")

        cancel_button = tk.Button(
            new_window,
            text="Cancel",
            font=("Arial", 10),
            bg="navy",
            fg="white",
            command=new_window.destroy,
        )
        cancel_button.grid(row=len(self.checks)+2, column=0, padx=10, pady=10, sticky="e")

        apply_button = tk.Button(
            new_window,
            text="Apply",
            font=("Arial", 10),
            bg="darkblue",
            fg="white",
            command=apply_changes,
        )
        apply_button.grid(row=len(self.checks)+2, column=1, padx=10, pady=10, sticky="w")
    
    def set_checks_channels_and_locks(self):
        # set all the channels for the checks, just in case the channels are not initialized
        for check in self.checks:
            check.set_channels(self.all_channels)
        # set all the devices locks for the checks, just in case the devices locks are not initialized
        for check in self.checks:
            if isinstance(check, MultiDeviceCheck):
                check.set_devices(self.all_locks)

    def check_conditions(self):
        failed_checks = []
        for i, check in enumerate(self.checks):
            frame_bg_color = self.frame.cget("bg")
            current_bg_color = self.checks_checkboxes[i].cget("bg")
            current_fg_color = self.checks_checkboxes[i].cget("fg")
            if not check.is_available():
                if current_bg_color != "gray":
                    self.checks_checkboxes[i].config(bg=frame_bg_color)
                if current_fg_color != "black":
                    self.checks_checkboxes[i].config(fg="black")
                continue
            if check.eval_condition():
                if current_fg_color != "green":
                    self.checks_checkboxes[i].config(fg="green")
                if current_bg_color != frame_bg_color:
                    self.checks_checkboxes[i].config(bg=frame_bg_color)
            else:
                all_available_checks_passed = False
                if current_fg_color != "black":
                    self.checks_checkboxes[i].config(fg="black")
                if current_bg_color != "red":
                    self.checks_checkboxes[i].config(bg="red")
                    print(f"Check '{check.name}' failed")
                    failed_checks.append(check)
        if failed_checks:
            message = "\n".join([f"Check '{check.name}' failed." for check in failed_checks])
            threading.Thread(
                target=lambda: messagebox.showwarning(
                    "Warning", message, parent=self.root
                )
            ).start() # show the warning in a new thread to avoid blocking the main thread until the warning is closed
        return failed_checks == []
    
    def simulate_check_conditions(self, parameters_values : dict):
        failed_checks = []
        for i, check in enumerate(self.checks):
            frame_bg_color = self.frame.cget("bg")
            current_bg_color = self.checks_checkboxes[i].cget("bg")
            current_fg_color = self.checks_checkboxes[i].cget("fg")
            if not check.is_available():
                if current_bg_color != "gray":
                    self.checks_checkboxes[i].config(bg=frame_bg_color)
                if current_fg_color != "black":
                    self.checks_checkboxes[i].config(fg="black")
                continue
            if check.simulate_eval_condition(parameters_values):
                if current_fg_color != "green":
                    self.checks_checkboxes[i].config(fg="green")
                if current_bg_color != frame_bg_color:
                    self.checks_checkboxes[i].config(bg=frame_bg_color)
            else:
                all_available_checks_passed = False
                if current_fg_color != "black":
                    self.checks_checkboxes[i].config(fg="black")
                if current_bg_color != "red":
                    self.checks_checkboxes[i].config(bg="red")
                    print(f"Check '{check.name}' failed")
                    failed_checks.append(check)
        if failed_checks:
            message = "\n".join([f"Simulated check '{check.name}' failed." for check in failed_checks])
            threading.Thread(
                target=lambda: messagebox.showwarning(
                    "Warning", message, parent=self.root
                )
            ).start() # show the warning in a new thread to avoid blocking the main thread until the warning is closed
        return failed_checks == []

    def check_loop(self):
        while True:
            self.check_conditions()
            time.sleep(2) # better to sleep for a while to avoid locking the devices with too many checks

    def start_background_threads(self):
        threading.Thread(target=self.check_loop, daemon=True).start()

if __name__ == "__main__":
    checks = [
        Check("Check 1", "ch1 > 10", {"ch1": 15}, "Check if ch1 is greater than 10"),
        Check("Check 2", "ch2 < 10", {"ch2": 5}, "Check if ch2 is less than 10"),
        Check("Check 3", "ch1 + ch2 == 20", {"ch1": 15, "ch2": 5}, "Check if ch1 + ch2 is equal to 20"),
    ]
    checks_frame = ChecksFrame(checks=checks)
