import tkinter as tk
import time
import argparse
import threading

import caengui
import spellmangui
import spellmanClass as spll
import hvps

from checkframe import ChecksFrame
from check import load_checks_from_toml_file

class HVGUI:
    def __init__(self, caen_module=None, spellman_module=None, checks_caen=None, checks_spellman=None, checks_multidevice=None):
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

        self.multidevice_frame = None
        self.checksframe = None
        self.channel_optmenus = None
        self.vset_entries = None
        self.factor_entries = None
        self.step_entry = None
        self.step_var = None

        self.create_gui()

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("TREX HV SC")

        if self.caen_module is not None:
            self.caen_frame = tk.Frame(self.root)
            self.caen_frame.pack(side="left", fill="both", expand=True)
            self.caen_gui = caengui.CaenHVPSGUI(module=self.caen_module, parent_frame=self.caen_frame,
                                                channel_names=caengui.CHANNEL_NAMES, checks=self.caen_checks, silence=False)
            self.all_channels = {name: self.caen_module.channels[n] for n, name in self.caen_gui.channel_names.items()}
            self.channels_gui = {name: self.caen_gui for name in self.caen_gui.channel_names.values()}
            self.all_guis['caen'] = self.caen_gui
            self.channels_vmon_guilabel = {name: label for name, label in zip(self.caen_gui.channel_names.values(), self.caen_gui.vmon_labels)}
            self.channels_vset_guientries = {name: entry for name, entry in zip(self.caen_gui.channel_names.values(), self.caen_gui.vset_entries)}

        if self.spellman_module is not None:
            self.spellman_frame = tk.Frame(self.root)
            self.spellman_frame.pack(side="right", fill=tk.BOTH, expand=True)
            self.spellman_gui = spellmangui.SpellmanFrame(spellman=self.spellman_module, parent=self.spellman_frame) # TODO: implement individual spellman checks
            self.all_channels = {'cathode' : self.spellman_module, **self.all_channels} # add the spellman module as cathode at the front of the dict
            self.channels_gui['cathode'] = self.spellman_gui
            self.all_guis['cathode'] = self.spellman_gui
            self.channels_vmon_guilabel['cathode'] = self.spellman_gui.labels['voltage_s']
            self.channels_vset_guientries['cathode'] = self.spellman_gui.labels['voltage_dac_s']
            
        if self.caen_module is not None and self.spellman_module is not None:
            self.create_multidevice_frame(self.spellman_frame)

        self.root.mainloop()

    def create_multidevice_frame(self, frame):
        self.multidevice_frame = tk.LabelFrame(frame, text="Multi-device control", font=("", 16), labelanchor="n", padx=10, pady=10, bd=4)
        self.multidevice_frame.pack(side="bottom", fill="both", expand=True)

        left_frame = tk.Frame(self.multidevice_frame)
        left_frame.pack(side="left", anchor="center")
        tk.Label(left_frame, text="Channel").grid(row=0, column=0)
        factor_label = tk.Label(left_frame, text="Factor")
        factor_label.grid(row=0, column=1)
        caengui.ToolTip(factor_label, "Factor to convert the voltage setpoint to the\nactual voltage you want to remain within the step.\n"
                                        "For example, the cathode voltage is divided by\n0.286=80MOhm/(200+80)MOhm to get\nthe last ring voltage.")
        tk.Label(left_frame, text="vset (V)").grid(row=0, column=2)
        def option_changed(row_number, *args):
            channel = self.channel_optmenus[row_number].cget("text")
            if channel == "":
                # hide the vset entry
                self.vset_entries[row_number].grid_remove()
                self.factor_entries[row_number].grid_remove()
                # make the option menu as small as possible and blank
                self.channel_optmenus[row_number].config(width=1)
                self.channel_optmenus[row_number].grid(sticky="")
                self.channel_optmenus[row_number].config(text="")

            else:
                # show if hidden
                self.vset_entries[row_number].grid()
                self.factor_entries[row_number].grid()
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

            factor_entry = tk.Entry(left_frame, justify="center", width=5)
            factor_entry.grid(row=i+1, column=1, padx=5)
            factor_entry.insert(0, "1" if ch_opt != "cathode" else "0.286") # 0.286 = 80MOhm/(200+80)MOhm to get last ring voltage (cathode voltage divider)
            self.factor_entries.append(factor_entry)

            vset_entry = tk.Entry(left_frame, justify="center", width=7)
            vset_entry.grid(row=i+1, column=2, padx=5)
            vset_entry.insert(0, self.channels_vset_guientries[ch_opt].get())
            self.vset_entries.append(vset_entry)

        tk.Label(left_frame, text="Step(V):").grid(row=n_rows+1, column=1, sticky="E", padx=0)
        self.step_var = tk.StringVar()
        step_entry = tk.Entry(left_frame, justify="right", width=5, textvariable=self.step_var)
        step_entry.grid(row=n_rows+1, column=2, sticky="W", padx=0)
        step_entry.insert(0, "100")
        self.step_entry = step_entry

        apply_button = tk.Button(left_frame, text="Apply", command= lambda: self.raise_voltage_protocol_thread(self.step_var.get()))
        apply_button.grid(row=n_rows+1, column=0, columnspan=2, pady=20)

        right_frame = tk.Frame(self.multidevice_frame, padx=10, pady=10)
        right_frame.pack(side="left", anchor="center", padx=20)
        all_devices_locks = tuple([gui.device_lock for gui in self.all_guis.values()])
        self.checksframe = ChecksFrame(right_frame, checks=self.checks, channels=self.all_channels, locks=all_devices_locks)

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

        threading.Thread(target=self.raise_voltage_protocol, args=(step_number,)).start()

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

        final_vset = {}
        factors = {}
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
        
        if len(final_vset) < 1: # makes no sense to use this with less than 2 channels
            print("No valid voltage setpoints found")
            return
        
        # check that all channels involved are on
        for ch in final_vset.keys():
            if ch not in self.all_channels.keys():
                print(f"Channel {ch} not found in the list of available channels")
                return
            with self.channels_gui[ch].device_lock:
                if not self.all_channels[ch].on:
                    print(f"Channel {ch} is off. Turn it on before running the protocol")
                    return

        if self.step_entry:
            self.step_entry.config(state="disabled")

        temp_vset = {k: 0 for k in final_vset.keys()} # initialize the temporary voltage setpoints

        max_vset = max([round(v*f) for v, f in zip(final_vset.values(), factors.values())])
        n_steps = int( max_vset / step ) + 1
        print(f"Number of steps: {n_steps}")
        vset = 0
        channels_reached = 0
        for _ in range(n_steps):
            vset = vset + step
            temp_vset = {k: round(vset/f) for k, f in zip(final_vset.keys(), factors.values())}
            if any([t >= f for t, f in zip(temp_vset.values(), final_vset.values())]):
                channels_reached += 1
            for ch, f in final_vset.items():
                temp_vset[ch] = f if temp_vset[ch] >= f else temp_vset[ch]
            print(f"Step {_+1}: {temp_vset}")

            # simulate the checks results before applying the new vsets
            parameters_values = {}
            for ch, v in temp_vset.items():
                parameters_values[ch.replace(" ", "") + ".vset"] = v
            # multidevice checks
            if not self.checksframe.simulate_check_conditions(parameters_values):
                print("Step did not pass the multidevice checks.")
                if self.step_entry:
                    self.step_entry.config(state="normal")
                return
            # individual device checks
            for device, gui in self.all_guis.items():
                try:
                    if not gui.checksframe.simulate_check_conditions(parameters_values):
                        print(f"Step did not pass the {device} checks.")
                        if self.step_entry:
                            self.step_entry.config(state="normal")
                        return
                except AttributeError:
                    pass

            # apply vsets to the channels
            for ch, v in temp_vset.items():
                if get_vmon(ch) > v:
                    print(f"Voltage monitor for channel {ch} is higher than the setpoint. Skipping the step.")
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
                    if self.step_entry:
                        self.step_entry.config(state="normal")
                    return
                # self.all_channels[ch].vset = v
            
            # wait for the channels to reach the setpoints
            all_channels_reached = False
            time_waiting = 0
            while not all_channels_reached:
                all_channels_reached = True
                for ch in temp_vset.keys():
                    vmon = get_vmon(ch)
                    if temp_vset[ch] - vmon > 13: # the spellman has 12V of precision...
                        all_channels_reached = False
                        break
                time.sleep(1) # wait 1 second before next check
                time_waiting += 1 # use same time as the number of seconds waited
                if time_waiting > timeout:
                    print("Timeout waiting for channels to reach the setpoints.")
                    break # pass to the next step

            time.sleep(5) # wait 3 seconds before next step

        if self.step_entry:
            self.step_entry.config(state="normal")

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
        app = HVGUI(caen_module=caen_module, spellman_module=spellman_module, checks_caen=checks_caen, checks_spellman=checks_spellman, checks_multidevice=checks_multidevice)


