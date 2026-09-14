import threading
import time
import random


# class that simulates the channel of the caen by giving a random value to its attributes vmon, imon and
class ChannelSimulator:
    def __init__(self, trip_probability=0.02):
        # private attributes (they do not exist in the real device)
        self._trip_probability = trip_probability
        self._vset = 100

        # public attributes (they exist in the real device)
        self.vset = 100
        self.iset = 0.6  # uA # functionality not implemented
        self.vmon = self.vset
        self.imon = self.vset / 10e3  # (uA) lets say there is a resistance of 10 MOhm
        self.imdec = 3  # channel imon number of decimal digits (2 HR, 3 LR)
        self.rup = 50  # V/s
        self.rdw = 10  # V/s
        self.pdwn = "RAMP"  # 'KILL' or 'RAMP'
        self.stat = {
            "ON": True,
            "RUP": False,
            "RDW": False,
            "OVC": False,
            "OVV": False,
            "UNV": False,
            "MAXV": False,
            "TRIP": False,
            "OVP": False,
            "OVT": False,
            "DIS": False,
            "KILL": False,
            "ILK": False,
            "NOCAL": False,
        }

    def _randomize(self):
        if self.stat["KILL"] or self.stat["DIS"]:
            self.stat["ON"] = False
            self.vmon = 0
            self.imon = 0
            return

        if self.stat["TRIP"] or self.stat["ILK"]:
            self.stat["ON"] = False
            if self.pdwn == "KILL":
                self.stat["KILL"] = (
                    True  # not sure if it behaves like this in KILL mode
                )
                self.vmon = 0
                self.imon = 0
                return

        self.vmon = random.gauss(self._vset, 1.0 / 3)  # 0.3 V standard deviation
        self.imon = random.gauss(
            self.vmon / 10e3, self.vmon / 100e3
        )  # (uA) lets say there is a resistance of 10 MOhm and 10% standard deviation

        if not self.stat["ON"]:
            self._vset -= self.rdw
            self.imon = -self.imon * 10
            # self.stat["RDW"] = True # not sure
            if self._vset <= 0:
                self._vset = 0
                self.vmon = 0
                self.imon = 0
            return

        if not self.stat["TRIP"]:
            self.stat["TRIP"] = random.random() < self._trip_probability

        # simulate ramp up and ramp down when the channel is ON
        if self._vset < self.vset:
            self.stat["RUP"] = True
            self.stat["RDW"] = False
            self._vset += self.rup
            self.imon = self.imon * 10
            if self._vset > self.vset:
                self._vset = self.vset
        elif self._vset > self.vset:
            self.stat["RDW"] = True
            self.stat["RUP"] = False
            self._vset -= self.rdw
            self.imon = -self.imon * 10
            if self._vset < self.vset:
                self._vset = self.vset
        else:
            self.stat["RUP"] = False
            self.stat["RDW"] = False

    def turn_on(self):
        self.stat["ON"] = True
        self.stat["TRIP"] = False
        self.stat["KILL"] = False
        self.stat["ILK"] = False

    def turn_off(self):
        self.stat["ON"] = False
        self.stat["KILL"] = False
        self.stat["TRIP"] = False
        self.stat["ILK"] = False  # not sure
    
    @property
    def on(self):
        return self.stat["ON"]
    
    def vset(self, voltage):
        self.vset = voltage



class ModuleSimulator:
    def __init__(self, n_channels, trip_probability=0.05):
        self.name = "N1471H SIMULATOR"
        self.number_of_channels = n_channels
        self.channels = [
            ChannelSimulator(
                1 - (1 - trip_probability) ** (1.0 / self.number_of_channels)
            )
            for i in range(self.number_of_channels)
        ]
        self.board_alarm_status = {
            "CH0": False,
            "CH1": False,
            "CH2": False,
            "CH3": False,
            "PWFAIL": False,
            "OVP": False,
            "HVCKFAIL": False,
        }
        self.interlock_status = False
        self.interlock_mode = "CLOSED"

        # Start the device reading thread
        self.randomize_thread = threading.Thread(
            target=self.__continuous_randomize, daemon=True
        ).start()

    def clear_alarm_signal(self):
        self.board_alarm_status = {k: False for k in self.board_alarm_status.keys()}
        for ch in self.channels:
            ch.stat["TRIP"] = False
            ch.stat["ILK"] = False

    def _randomize(self):
        # print(self.board_alarm_status, self.interlock_status)
        # check for trips and set the alarm signal
        for i, ch in enumerate(self.channels):
            if ch.stat["TRIP"]:
                self.board_alarm_status["CH" + str(i)] = True
                # print(f"Channel {i} trip")

        # do the alarm-intlck connection and act the interlock
        self.__connection_alarm_intlck()
        if self.interlock_status:
            for ch in self.channels:
                ch.stat["ILK"] = True

        # randomize the channels
        for ch in self.channels:
            ch._randomize()

    def __continuous_randomize(self, wait_seconds=1):
        while True:
            self._randomize()
            time.sleep(wait_seconds)

    def __connection_alarm_intlck(self):
        self.interlock_status = any([v for k, v in self.board_alarm_status.items()])



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


class RigolChannelSimulator:
    def __init__(self, channel_number, trip_probability=0.01):
        self.channel_number = channel_number
        self.trip_probability = trip_probability
        self.vset = 5.0  # V
        self.iset = 0.6  # A
        self.vmon = self.vset
        self.imon = self.vset / 10e3  # (A) lets say there is a resistance of 10 Ohm
        self.powermon = self.vmon * self.imon 
        self.on = True

    def _randomize(self):
        if not self.on:
            self.vmon = 0
            self.imon = 0
            self.powermon = 0
            return

        self.vmon = random.gauss(self.vset, 0.1)  # 0.1 V standard deviation
        self.imon = random.gauss(1, 0.1)
        self.powermon = self.vmon * self.imon  # W

    def turn_on(self):
        self.on = True

    def turn_off(self):
        self.on = False

class RigolSimulator:
    def __init__(self, name="Rigol DP832 SIMULATOR"):
        self.name = name
        self.number_of_channels = 3
        self.channels = [RigolChannelSimulator(channel_number=i+1) for i in range(self.number_of_channels)]
        self.instrument = True  # Simulate an open connection

    def __enter__(self):
        # Simulate opening a connection
        self.instrument = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Simulate closing a connection
        self.instrument = None

    def get_channel(self, channel_number):
        # Channel numbers are 1-based, as in the real device (":MEAS:ALL? CH1")
        if not 1 <= channel_number <= self.number_of_channels:
            raise ValueError(
                f"Invalid channel number {channel_number}:"
                f" expected 1 to {self.number_of_channels}"
            )
        return self.channels[channel_number - 1]

    def turn_on_channel(self, channel_number):
        self.get_channel(channel_number).turn_on()

    def turn_off_channel(self, channel_number):
        self.get_channel(channel_number).turn_off()

    def measure_all(self, channel_number):
        channel = self.get_channel(channel_number)
        channel._randomize()
        return {
            "voltage": round(channel.vmon, 2),
            "current": round(channel.imon, 3),
            "power": round(channel.powermon, 2),
        }

    def get_output_state(self, channel_number):
        return "ON" if self.get_channel(channel_number).on else "OFF"

# class that simulates the MX32v2 gas controller. It takes the same SensorConfig
# objects as the real device (see mx32v2.py), but it is not imported from there so
# that the simulators stay usable without pymodbus installed.
class MX32v2Simulator:
    def __init__(self, name="MX32v2 SIMULATOR", leak_probability=0.05, fault_probability=0.02):
        self.name = name
        self.slave_id = 0
        self.leak_probability = leak_probability
        self.fault_probability = fault_probability
        self._concentrations = {}
        self._leaking = {}

    def connect(self):
        return True

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _randomize(self, sensor):
        # random walk that goes up while "leaking" and slowly vents otherwise, so
        # the three alarm levels are crossed every now and then
        concentration = self._concentrations.get(sensor.name, 0.0)
        if self._leaking.get(sensor.name, False):
            concentration += random.uniform(0, 0.1 * sensor.range_max)
            if random.random() < 0.3:
                self._leaking[sensor.name] = False
        else:
            concentration -= random.uniform(0, 0.05 * sensor.range_max)
            if random.random() < self.leak_probability:
                self._leaking[sensor.name] = True

        concentration = min(max(concentration, 0.0), sensor.range_max)
        self._concentrations[sensor.name] = concentration
        return concentration

    def read_sensor(self, sensor):
        concentration = self._randomize(sensor)
        values = {
            "concentration": round(concentration, 1),
            "alarm1": False,
            "alarm2": False,
            "alarm3": False,
            "under_range": False,
            "over_range": concentration >= sensor.range_max,
            "fault": random.random() < self.fault_probability,
            "out_of_range": False,
            "maintenance": False,
            "comm_ok": True,
        }
        for alarm in sensor.alarms:
            values[alarm.key] = concentration >= alarm.level
        return values


class ArduinoSimulator:
    """
    Simulator of the Arduino reading the digital alarm signals of the safety
    system: 0 is the quiet state and 1 is the alarm being raised.
    """

    def __init__(self, name="Arduino SIMULATOR", number_of_signals=2,
                 alarm_probability=0.02, clear_probability=0.3, no_data_probability=0.02):
        self.name = name
        self.number_of_signals = number_of_signals
        self.alarm_probability = alarm_probability
        self.clear_probability = clear_probability
        self.no_data_probability = no_data_probability
        self.timeout = 2
        self.ser = True  # simulate an open connection
        self._signals = [0] * number_of_signals

    def open(self):
        self.ser = True

    def close(self):
        self.ser = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _randomize(self):
        for i, signal in enumerate(self._signals):
            if signal:
                if random.random() < self.clear_probability:
                    self._signals[i] = 0
            elif random.random() < self.alarm_probability:
                self._signals[i] = 1
        return tuple(self._signals)

    def get_both(self):
        # the real reader returns None when no valid line was received before the timeout
        if random.random() < self.no_data_probability:
            return None
        return self._randomize()

    def get_signal(self, signal_number):
        if signal_number not in range(1, self.number_of_signals + 1):
            print(f"Invalid signal number. Use 1 to {self.number_of_signals}.")
            return None
        signals = self.get_both()
        return signals[signal_number - 1] if signals else None

    def get_signal1(self):
        return self.get_signal(1)

    def get_signal2(self):
        return self.get_signal(2)
