import tkinter as tk
import argparse

# import spellmanModule as spll  # Assuming spellmanModule has required functions
from spellmanClass import Spellman
from logger import ChannelState
from checkframe import ChecksFrame
from devicegui import DeviceGUI

class SpellmanFrame(DeviceGUI):
    def __init__(self, spellman, checks=None, parent=None, log=True):
        if checks is None:
            checks = []

        self.checks = checks
        self.buttons = {}
        self.labels = {}
        self.label_vars = {}
        self.security_frame = None

        super().__init__(spellman, ['cathode'], parent,
                        logging_enabled=log,
                        channel_state_save_previous=False,
                        channel_state_diff_vmon=50,
                        channel_state_diff_imon=999,
                        channel_state_prec_vmon=0,
                        channel_state_prec_imon=5,
                        read_loop_time=2,
                        )

    def create_gui(self):
        self.main_frame = tk.LabelFrame(
            self.root, text=f"{self.device.name}", font=("", 16), bg="lightgray",
            labelanchor="n", padx=10, pady=10, bd=4
        )
        self.main_frame.pack(fill="both", expand=True)

        # Create GUI components
        self.buttons, self.labels = self.makeremotebar_s(self.main_frame, self.buttons, self.labels)
        self.buttons, self.labels = self.makehvbar_s(self.main_frame, self.buttons, self.labels)
        self.labels.update(self.maketable_s(self.main_frame))
        #self.buttons, self.labels = self.makedac_s(self.main_frame, self.buttons, self.labels)
        self.makecalc(self.main_frame, self.labels)
        self.security_frame = self.create_security_frame(self.main_frame)

        self.start_background_threads()

    def makeremotebar_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.grid(row=0, column=0, sticky='nw', padx=5, pady=5)

        etiqueta_text = tk.Label(marco, text='    REMOTE : ', width=10)
        etiqueta = tk.Label(marco, text=' -- ', width=5)
        boton_remote_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.turn_remote_on), width=3)
        boton_remote_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.turn_remote_off), width=3)

        etiqueta_text.grid(row=0, column=0, sticky='w')
        etiqueta.grid(row=0, column=1)
        boton_remote_on.grid(row=0, column=2)
        boton_remote_off.grid(row=0, column=3)

        labels['remote_s'] = etiqueta
        botones['remote_on_s'] = boton_remote_on
        botones['remote_off_s'] = boton_remote_off

        return botones, labels

    def makehvbar_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.grid(row=0, column=1, sticky='nw', padx=5, pady=5)

        etiqueta_text = tk.Label(marco, text='    HV   : ', width=10)
        etiqueta = tk.Label(marco, text=' -- ', width=5)
        boton_hv_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.turn_hv_on), width=3)
        boton_hv_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.turn_hv_off), width=3)

        etiqueta_text.grid(row=0, column=0, sticky='w')
        etiqueta.grid(row=0, column=1)
        boton_hv_on.grid(row=0, column=2)
        boton_hv_off.grid(row=0, column=3)

        labels['hv'] = etiqueta
        botones['hv_on'] = boton_hv_on
        botones['hv_off'] = boton_hv_off

        return botones, labels

    def maketable_s(self, win):
        marco = tk.Frame(win)
        marco.grid(row=2, column=0, columnspan=2, sticky='nw', padx=5, pady=5)

        tk.Label(marco, text='Set', width=10).grid(row=0, column=3)
        tk.Label(marco, text='Monitor', width=10).grid(row=0, column=4)

        voltage_text = tk.Label(marco, text='Voltage (V) : ', width=11)
        voltage_var = tk.StringVar()
        voltage_var.trace_add("write", self.update_last_rings)
        voltage_label = tk.Label(marco, text='-----', width=8, textvariable=voltage_var)
        current_text = tk.Label(marco, text='Current (mA): ', width=11)
        current_label = tk.Label(marco, text='-----', width=8)
        arc_text = tk.Label(marco, text='Arc : ', width=11)
        arc_label = tk.Label(marco, text='Arc')

        voltage_text.grid(row=1, column=0, sticky='nse')
        voltage_label.grid(row=1, column=4)
        current_text.grid(row=2, column=0, sticky='nse')
        current_label.grid(row=2, column=4)
        arc_text.grid(row=3, column=0, sticky='nse')
        arc_label.grid(row=3, column=1, sticky='nsw')


        

        voltage_dac_entry = tk.Entry(marco, width=8, justify='right')
        voltage_dac_entry.insert(0, f"{self.device.vset:.0f}")
        voltage_dac_entry.bind(
            "<Return>", lambda event: self.issue_command(self.set_vset)
        )
        voltage_dac_set = tk.Button(marco, text='SET', command=lambda: self.issue_command(self.set_vset), width=3)

        voltage_dac_entry.grid(row=1, column=2, sticky='nsw', padx=0)
        voltage_dac_set.grid(row=1, column=1, sticky='nse', padx=0)
        current_dac_entry = tk.Entry(marco, width=8, justify='right')
        current_dac_entry.insert(0, f"{self.device.iset:.5f}")
        current_dac_entry.bind(
            "<Return>", lambda event: self.issue_command(self.set_iset)
        )
        current_dac_set = tk.Button(marco, text='SET', command=lambda: self.issue_command(self.set_iset), width=3)

        current_dac_entry.grid(row=2, column=2, sticky='nsw', padx=0)
        current_dac_set.grid(row=2, column=1, sticky='nse', padx=0)

        voltage_dac_label = tk.Label(marco, width=10, justify='right', text='Vset(V)')
        voltage_dac_label.grid(row=1, column=3, sticky='ns')

        current_dac_label = tk.Label(marco, width=10, justify='right', text='Iset(mA)')
        current_dac_label.grid(row=2, column=3, sticky='ns')

        diccionario_labels = {
            'voltage_s': voltage_label,
            'current_s': current_label,
            'arc': arc_label,
            'voltage_dac_s': voltage_dac_entry,
            'current_dac_s': current_dac_entry,
            'voltage_dac_label': voltage_dac_label,
            'current_dac_label': current_dac_label,
        }
        self.label_vars['voltage'] = voltage_var
        return diccionario_labels

    def makecalc(self, win, labels):
        marco = tk.LabelFrame(win, text='Last ring values', padx=10, pady=10)
        marco.grid(row=3, column=0, sticky='ew', padx=5, pady=5)

        voltage_label = tk.Label(marco, text='Voltage(V)')
        voltage_label.grid(row=1, column=0)
        current_label = tk.Label(marco, text='Current(mA)')
        current_label.grid(row=2, column=0)


        left_label = tk.Label(marco, text='Left')
        left_label.grid(row=0, column=1)
        lastring_v_left_label = tk.Label(marco, text='', width=10)
        lastring_v_left_label.grid(row=1, column=1)
        lastring_i_left_label = tk.Label(marco, text='', width=10)
        lastring_i_left_label.grid(row=2, column=1)


        right_label = tk.Label(marco, text='Right')
        right_label.grid(row=0, column=2)
        lastring_v_right_label = tk.Label(marco, text='', width=10)
        lastring_v_right_label.grid(row=1, column=2)
        lastring_i_right_label = tk.Label(marco, text='', width=10)
        lastring_i_right_label.grid(row=2, column=2)

        self.labels['lastring_v_left'] = lastring_v_left_label
        self.labels['lastring_i_left'] = lastring_i_left_label
        self.labels['lastring_v_right'] = lastring_v_right_label
        self.labels['lastring_i_right'] = lastring_i_right_label

    def create_security_frame(self, frame):
        security_frame = tk.Frame(frame)
        security_frame.grid(row=3, column=1, sticky='ew', padx=5, pady=5)
        channels = {self.channels_name[0] : self.device}
        locks = tuple([self.device_lock])
        self.checksframe = ChecksFrame(security_frame, checks=self.checks, channels=channels, locks=locks)
        return security_frame

    def turn_remote_on(self):
        self.device.turn_remote_on()

    def turn_remote_off(self):
        self.device.turn_remote_off()

    def turn_hv_on(self):
        self.device.turn_hv_on()

    def turn_hv_off(self):
        self.device.turn_hv_off()

    def set_vset(self, check=True):
        # entry formatting
        try:
            vset_value = float(self.labels['voltage_dac_s'].get())
        except ValueError:
            self.labels['voltage_dac_s'].delete(0, tk.END)
            self.labels['voltage_dac_s'].insert(0, f"{self.device.get_vset():.0f}")
            print("ValueError: Set voltage value must be a number")
            return

        # simulate the checks with the change in the vset value
        parameters_values = {self.channels_name[0].replace(" ", "") +".vset" : vset_value}
        if check and self.checksframe is not None:
            self.labels['voltage_dac_s'].config(state='readonly') # to avoid manual changes while checking
            if not self.checksframe.simulate_check_conditions(parameters_values):
                self.labels['voltage_dac_s'].config(fg='red')
                self.labels['voltage_dac_s'].config(state='normal')
                return False
            else:
                self.labels['voltage_dac_s'].config(fg='black')
                self.labels['voltage_dac_s'].config(state='normal')

        # finally set the value
        self.device.vset = vset_value
        return True

    def set_iset(self):
        # entry formatting
        try:
            iset_value = float(self.labels['current_dac_s'].get())
        except ValueError:
            self.labels['current_dac_s'].delete(0, tk.END)
            self.labels['current_dac_s'].insert(0, f"{self.device.get_iset():.5f}")
            print("ValueError: Set current value must be a number")
            return

        # simulate the checks with the change in the iset value
        parameters_values = {self.channels_name[0].replace(" ", "") +".iset" : iset_value}
        if self.checksframe is not None:
            self.labels['current_dac_s'].config(state='readonly')
            if not self.checksframe.simulate_check_conditions(parameters_values):
                self.labels['current_dac_s'].config(fg='red')
                self.labels['current_dac_s'].config(state='normal')
                return False
            else:
                self.labels['current_dac_s'].config(fg='black')
                self.labels['current_dac_s'].config(state='normal')

        # finally set the value
        self.device.iset = iset_value
        return True

    def update_last_rings(self, *args):
        vmon_str = self.label_vars['voltage'].get()
        vmon = float(vmon_str)
        left_resitance = 80 # MOhm
        right_resitance = 50 # MOhm

        imon_left = vmon / (200 + left_resitance) / 1000 # mA
        vmon_left = imon_left * left_resitance * 1000 # V

        imon_right = vmon / (200 + right_resitance) / 1000 # mA
        vmon_right = imon_right * right_resitance * 1000 # V

        self.labels['lastring_v_left'].config(text=f"{vmon_left:.0f}")
        self.labels['lastring_i_left'].config(text=f"{imon_left:.5f}")

        self.labels['lastring_v_right'].config(text=f"{vmon_right:.0f}")
        self.labels['lastring_i_right'].config(text=f"{imon_right:.5f}")

    def read_values(self):
        vmon = self.device.vmon
        imon = self.device.imon
        vset = self.device.vset
        iset = self.device.iset
        self.channels_state[0].set_state(vmon, imon)
        self.label_vars['voltage'].set(f"{vmon:.0f}")
        self.labels['current_s'].config(text=f"{imon:.5f}")
        self.labels['voltage_dac_label'].config(text=f"{vset:.0f}")
        self.labels['current_dac_label'].config(text=f"{iset:.5f}")

        stat = self.device.stat
        remote = stat['REMOTE']
        hv = stat['HV']

        if isinstance(remote, bool):
            self.labels['remote_s'].config(text='ON' if remote else 'OFF')
            self.labels['remote_s'].config(fg='green' if remote else 'red')
        else:
            self.labels['remote_s'].config(text=remote)
            self.labels['remote_s'].config(fg='black')

        if isinstance(hv, bool):
            self.labels['hv'].config(text='ON' if hv else 'OFF')
            self.labels['hv'].config(fg='green' if hv else 'red')
        else:
            self.labels['hv'].config(text=hv)
            self.labels['hv'].config(fg='black')


# Usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Enable test mode")
    parser.add_argument("--port", type=int, help="Select port", default=50001)
    parser.add_argument("--host", type=str, help="Select host", default='192.168.17.1')

    args = parser.parse_args()

    if not args.test:
        spll = Spellman(args.host, args.port)
        app = SpellmanFrame(spll)
    else:
        from simulators import SpellmanSimulator
        spll = SpellmanSimulator()
        app = SpellmanFrame(spll, log=False)

