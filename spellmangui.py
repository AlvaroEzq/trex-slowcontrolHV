import tkinter as tk
import queue
import threading
import time
import argparse

# import spellmanModule as spll  # Assuming spellmanModule has required functions
from spellmanClass import Spellman

class SpellmanFrame:
    def __init__(self, spellman, parent=None):
        self.spellman = spellman
        self.buttons = {}
        self.labels = {}
        if parent is None:
            self.root = tk.Tk()
            self.root.title('TREX-DM' + ' ' + 'version')  # Replace 'version' with the actual version variable
        else:
            self.root = parent

        self.command_queue = queue.Queue()
        self.device_lock = threading.Lock()

        self.create_frame()

        if parent is None:
            self.root.mainloop()

    def create_frame(self):
        self.main_frame = tk.LabelFrame(self.root, text='SPELLMAN', font=("",16), bg="lightgray", labelanchor="n", padx=10, pady=10, bd=4)
        self.main_frame.pack()

        # Create GUI components
        self.buttons, self.labels = self.makeremotebar_s(self.main_frame, self.buttons, self.labels)
        self.buttons, self.labels = self.makehvbar_s(self.main_frame, self.buttons, self.labels)
        self.labels.update(self.maketable_s(self.main_frame))
        self.buttons, self.labels = self.makedac_s(self.main_frame, self.buttons, self.labels)

        self.start_background_threads()

    def makeremotebar_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.pack(side='top', anchor='ne')
        etiqueta_text = tk.Label(marco, text='    REMOTE : ', width=10)
        etiqueta = tk.Label(marco, text=' -- ', width=5)
        boton_remote_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.remote_on), width=3)
        boton_remote_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.remote_off), width=3)
        etiqueta_text.pack(side='left')
        etiqueta.pack(side='left')
        boton_remote_on.pack(side='left')
        boton_remote_off.pack(side='left')
        labels['remote_s'] = etiqueta
        botones['remote_on_s'] = boton_remote_on
        botones['remote_off_s'] = boton_remote_off
        return botones, labels

    def makehvbar_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.pack(side='top', anchor='nw')
        etiqueta_text = tk.Label(marco, text='    HV   : ', width=10)
        etiqueta = tk.Label(marco, text=' -- ', width=5)
        boton_hv_on = tk.Button(marco, text='ON', command=lambda: self.issue_command(self.hv_on), width=3)
        boton_hv_off = tk.Button(marco, text='OFF', command=lambda: self.issue_command(self.hv_off), width=3)
        etiqueta_text.pack(side='left')
        etiqueta.pack(side='left')
        boton_hv_on.pack(side='left')
        boton_hv_off.pack(side='left')
        labels['hv'] = etiqueta
        botones['hv_on'] = boton_hv_on
        botones['hv_off'] = boton_hv_off
        return botones, labels

    def maketable_s(self, win):
        marco = tk.Frame(win)
        marco.pack(side='left')
        # Rows
        marco1 = tk.Frame(marco)
        marco1.pack()
        marco2 = tk.Frame(marco)
        marco2.pack()
        marco3 = tk.Frame(marco)
        marco3.pack()
        voltage_text = tk.Label(marco1, text='Voltage(V) : ', width=14)
        voltage_label = tk.Label(marco1, text='-----', width=12)
        current_text = tk.Label(marco2, text='Current(mA): ', width=14)
        current_label = tk.Label(marco2, text='-----', width=12)
        arc_text = tk.Label(marco3, text='Arc : ', width=14)
        arc_label = tk.Label(marco3, text='Arc', width=12)
        voltage_text.pack(side='left')
        voltage_label.pack(side='left')
        current_text.pack(side='left')
        current_label.pack(side='left')
        arc_text.pack(side='left')
        arc_label.pack(side='left')
        diccionario_labels = {}
        diccionario_labels['voltage_s'] = voltage_label
        diccionario_labels['current_s'] = current_label
        diccionario_labels['arc'] = arc_label
        return diccionario_labels

    def makedac_s(self, win, botones, labels):
        marco = tk.Frame(win)
        marco.pack(side='top')
        
        marco1 = tk.Frame(marco)
        marco1.pack()
        marco2 = tk.Frame(marco)
        marco2.pack()
        
        # Voltage DAC Entry
        voltage_dac_text = tk.Label(marco1, text='Voltage DAC(V) : ', width=14)
        voltage_dac_entry = tk.Entry(marco1, width=6, justify='right')
        voltage_dac_entry.insert(0, str(self.spellman.vset))
        voltage_dac_entry.bind(
                "<Return>", lambda event: self.issue_command(self.set_vset)
            )
        voltage_dac_set = tk.Button(marco1, text='SET', command=lambda: self.issue_command(self.set_vset), width=3)
        
        voltage_dac_text.pack(side='left')
        voltage_dac_entry.pack(side='left')
        voltage_dac_set.pack(side='left')
        
        # Current DAC Entry
        current_dac_text = tk.Label(marco2, text='Current DAC(mA): ', width=14)
        current_dac_entry = tk.Entry(marco2, width=6, justify='right')
        current_dac_entry.insert(0, str(self.spellman.iset))
        current_dac_entry.bind(
                "<Return>", lambda event: self.issue_command(self.set_iset)
            )
        current_dac_set = tk.Button(marco2, text='SET', command=lambda: self.issue_command(self.set_iset), width=3)
        
        current_dac_text.pack(side='left')
        current_dac_entry.pack(side='left')
        current_dac_set.pack(side='left')
        
        # Store entries in the labels dictionary
        labels['voltage_dac_s'] = voltage_dac_entry
        labels['current_dac_s'] = current_dac_entry
        
        return botones, labels

    def start_background_threads(self):
        threading.Thread(target=self.read_loop, daemon=True).start()
        threading.Thread(target=self.process_commands, daemon=True).start()

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

    # Stub methods for buttons (replace with actual implementations)
    def remote_on(self):
        self.spellman.remote_on()

    def remote_off(self):
        self.spellman.remote_off()

    def hv_on(self):
        self.spellman.hv_on()

    def hv_off(self):
        self.spellman.hv_off()

    def set_vset(self):
        try:
            vset_value = float(self.labels['voltage_dac_s'].get())
        except ValueError:
            self.labels['voltage_dac_s'].delete(0, tk.END)
            self.labels['voltage_dac_s'].insert(0, str(self.spellman.get_vset()))
            print("ValueError: Set voltage value must be a number")
            return
        self.spellman.vset = vset_value

    def set_iset(self):
        try:
            iset_value = float(self.labels['current_dac_s'].get())
        except ValueError:
            self.labels['current_dac_s'].delete(0, tk.END)
            self.labels['current_dac_s'].insert(0, str(self.spellman.get_iset()))
            print("ValueError: Set current value must be a number")
            return
        self.spellman.iset = iset_value
    
    def read_values(self):
        vmon = self.spellman.vmon
        imon = self.spellman.imon
        self.labels['voltage_s'].config(text=f"{vmon:.0f}")
        self.labels['current_s'].config(text=f"{imon:.5f}")

        stat = self.spellman.stat
        remote = stat['REMOTE']
        hv = stat['HV']

        if isinstance(remote, bool):
            self.labels['remote_s'].config(text= 'ON' if remote else 'OFF')
        else:
            self.labels['remote_s'].config(text= remote)

        if isinstance(hv, bool):
            self.labels['hv'].config(text= 'ON' if hv else 'OFF')
        else:
            self.labels['hv'].config(text= hv)


    def read_loop(self):
        while True:
            self.issue_command(self.read_values)
            time.sleep(2)

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

