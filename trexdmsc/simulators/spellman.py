import threading
import time
import random


class SpellmanSimulator:
    def __init__(self):
        self.server_host = "ip"
        self.server_port = 50001
        self.name = 'Spellman SL30 SIMULATOR'
        self.vset = 0 # V
        self.iset = 0
        self.vmon = 0 # mA
        self.imon = 0
        self.stat = {'HV': True, 'ILK': False, 'FAULT': False, 'REMOTE': True, 'ARC': False}

        # start the device reading thread
        self.randomize_thread = threading.Thread(target=self.__continuous_randomize, daemon=True).start()

    def __continuous_randomize(self, wait_seconds=1):
        while True:
            self._randomize()
            time.sleep(wait_seconds)
    
    def _randomize(self):
        if not self.stat['REMOTE']:
            return

        if self.stat['HV']:
            self.vmon = random.gauss(self.vset, 3)
            Rleft = 200 + 80 # MOhm
            Rright = 200 + 50 # Mohm
            imon_mean = self.vmon * (1 / Rleft + 1 / Rright) *1e-3 # mA
            self.imon = random.gauss(imon_mean, imon_mean *0.01)
        else:
            self.vmon = 0
            self.imon = 0

    def get_vset(self):
        return self.vset
    
    def set_vset(self, voltage_V):
        self.vset = voltage_V
    
    def get_iset(self):
        return self.iset
    
    def set_iset(self, current_mA):
        self.iset = current_mA
    
    def get_vmon(self):
        return self.vmon
    
    def get_imon(self):
        return self.imon
    
    def get_status(self):
        return self.stat
    
    def turn_remote_on(self):
        self.stat['REMOTE'] = True
    
    def turn_remote_off(self):
        self.stat['REMOTE'] = False
    
    def turn_hv_on(self):
        self.stat['HV'] = True
    
    def turn_hv_off(self):
        self.stat['HV'] = False
    
    def turn_on(self):
        self.turn_hv_on()

    def turn_off(self):
        self.turn_hv_off()

    def status(self):
        return self.stat
    
    @property
    def on(self):
        return self.get_status()['HV']

    @property
    def remote(self):
        return self.get_status()['REMOTE']
    
    def vset(self, voltage):
        self.set_vset(voltage)
