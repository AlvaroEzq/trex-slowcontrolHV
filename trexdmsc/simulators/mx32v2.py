import random


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
