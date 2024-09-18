import tkinter as tk
import argparse

# import spellmanModule as spll  # Assuming spellmanModule has required functions
from spellmanClass import Spellman
from logger import ChannelState
from devicegui import DeviceGUI

class SpellmanFrame(DeviceGUI):
    def __init__(self, spellman, parent=None):
        self.buttons = {}
        self.labels = {}
        self.label_vars = {}
        self.channels_state_save_previous = False
        self.channels_state_diff_vmon = 15
        self.channels_state_diff_imon = 999
        self.channels_state_prec_vmon = 0
        self.channels_state_prec_imon = 5
        self.read_loop_time = 2  # seconds
        super().__init__(spellman, ['cathode'], parent)

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
        self.buttons, self.labels = self.makedac_s(self.main_frame, self.buttons, self.labels)
        self.makecalc(self.main_frame, self.labels)

        self.start_background_threads()

    def makeremotebar_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.grid(row=0, column=0, sticky='nw', padx=5, pady=5)

        etiqueta_text = tk.Label(marco, text='    REMOTE : ', width=10)
        etiqueta = tk.Label(marco, text=' -- ', width=5)
        boton_remote_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.remote_on), width=3)
        boton_remote_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.remote_off), width=3)

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
        boton_hv_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.hv_on), width=3)
        boton_hv_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.hv_off), width=3)

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
        marco.grid(row=2, column=0, sticky='nw', padx=5, pady=5)

        marco1 = tk.Frame(marco)
        marco1.grid(row=0, column=0, pady=2)
        marco2 = tk.Frame(marco)
        marco2.grid(row=1, column=0, pady=2)
        marco3 = tk.Frame(marco)
        marco3.grid(row=2, column=0, pady=2)

        voltage_text = tk.Label(marco1, text='Voltage(V) : ', width=14)
        voltage_var = tk.StringVar()
        voltage_var.trace_add("write", self.update_last_rings)
        voltage_label = tk.Label(marco1, text='-----', width=12, textvariable=voltage_var)
        current_text = tk.Label(marco2, text='Current(mA): ', width=14)
        current_label = tk.Label(marco2, text='-----', width=12)
        arc_text = tk.Label(marco3, text='Arc : ', width=14)
        arc_label = tk.Label(marco3, text='Arc', width=12)

        voltage_text.grid(row=0, column=0, sticky='w')
        voltage_label.grid(row=0, column=1)
        current_text.grid(row=0, column=0, sticky='w')
        current_label.grid(row=0, column=1)
        arc_text.grid(row=0, column=0, sticky='w')
        arc_label.grid(row=0, column=1)

        diccionario_labels = {
            'voltage_s': voltage_label,
            'current_s': current_label,
            'arc': arc_label
        }
        self.label_vars['voltage'] = voltage_var
        return diccionario_labels

    def makedac_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.grid(row=2, column=1, sticky='nw', padx=5, pady=5)

        marco1 = tk.Frame(marco)
        marco1.grid(row=0, column=0, pady=2)
        marco2 = tk.Frame(marco)
        marco2.grid(row=1, column=0, pady=2)

        voltage_dac_text = tk.Label(marco1, text='Voltage DAC(V) : ', width=14)
        voltage_dac_entry = tk.Entry(marco1, width=10, justify='right')
        voltage_dac_entry.insert(0, f"{self.device.vset:.0f}")
        voltage_dac_entry.bind(
            "<Return>", lambda event: self.issue_command(self.set_vset)
        )
        voltage_dac_set = tk.Button(marco1, text='SET', command=lambda: self.issue_command(self.set_vset), width=3)

        voltage_dac_text.grid(row=0, column=0, sticky='w')
        voltage_dac_entry.grid(row=0, column=1)
        voltage_dac_set.grid(row=0, column=2)

        current_dac_text = tk.Label(marco2, text='Current DAC(mA): ', width=14)
        current_dac_entry = tk.Entry(marco2, width=10, justify='right')
        current_dac_entry.insert(0, f"{self.device.iset:.5f}")
        current_dac_entry.bind(
            "<Return>", lambda event: self.issue_command(self.set_iset)
        )
        current_dac_set = tk.Button(marco2, text='SET', command=lambda: self.issue_command(self.set_iset), width=3)

        current_dac_text.grid(row=0, column=0, sticky='w')
        current_dac_entry.grid(row=0, column=1)
        current_dac_set.grid(row=0, column=2)

        labels['voltage_dac_s'] = voltage_dac_entry
        labels['current_dac_s'] = current_dac_entry

        return botones, labels

    def makecalc(self, win, labels):
        marco = tk.LabelFrame(win, text='Last ring values', padx=10, pady=10)
        marco.grid(row=3, column=0, columnspan=2, sticky='ew', padx=5, pady=5)

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

    def remote_on(self):
        self.device.remote_on()

    def remote_off(self):
        self.device.remote_off()

    def hv_on(self):
        self.device.hv_on()

    def hv_off(self):
        self.device.hv_off()

    def set_vset(self):
        try:
            vset_value = float(self.labels['voltage_dac_s'].get())
        except ValueError:
            self.labels['voltage_dac_s'].delete(0, tk.END)
            self.labels['voltage_dac_s'].insert(0, f"{self.device.get_vset():.0f}")
            print("ValueError: Set voltage value must be a number")
            return
        self.device.vset = vset_value

    def set_iset(self):
        try:
            iset_value = float(self.labels['current_dac_s'].get())
        except ValueError:
            self.labels['current_dac_s'].delete(0, tk.END)
            self.labels['current_dac_s'].insert(0, f"{self.device.get_iset():.5f}")
            print("ValueError: Set current value must be a number")
            return
        self.device.iset = iset_value

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
        self.channels_state[0].set_state(vmon, imon)
        self.label_vars['voltage'].set(f"{vmon:.0f}")
        self.labels['current_s'].config(text=f"{imon:.5f}")

        stat = self.device.stat
        remote = stat['REMOTE']
        hv = stat['HV']

        if isinstance(remote, bool):
            self.labels['remote_s'].config(text='ON' if remote else 'OFF')
        else:
            self.labels['remote_s'].config(text=remote)

        if isinstance(hv, bool):
            self.labels['hv'].config(text='ON' if hv else 'OFF')
        else:
            self.labels['hv'].config(text=hv)


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
        app = SpellmanFrame(spll)

