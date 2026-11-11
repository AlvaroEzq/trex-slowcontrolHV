import math
import random


class MaxiGaugeSimulator:
    """
    Simulator of the MaxiGauge. It takes the same GaugeConfig objects as the real
    device (see devices/maxigauge.py), but it is not imported from there so that the
    simulators stay independent of the device modules.

    The channels in 'connected' random walk in log scale around a vacuum pressure
    (with rare pressure bursts), the others answer 'No sensor' (status 5).
    """

    def __init__(self, name="MaxiGauge SIMULATOR", connected=(1, 2), burst_probability=0.01,
                 failure_probability=0.01):
        self.name = name
        self.burst_probability = burst_probability
        self.failure_probability = failure_probability
        self._log_pressure = {channel: random.uniform(-4, -2) for channel in connected}

    def read_channel(self, channel):
        if not 1 <= channel <= 6:
            raise ValueError(f"Channel must be 1 to 6, not {channel}")
        if random.random() < self.failure_probability:
            raise ConnectionError(f"{self.name}: simulated communication failure")
        if channel not in self._log_pressure:
            return 5, 0.0
        log_pressure = self._log_pressure[channel]
        if random.random() < self.burst_probability:
            log_pressure = random.uniform(0.5, 2) # up to 100 mbar: alarm
        else:
            # relax towards 1e-3 mbar
            log_pressure += 0.3 * (-3 - log_pressure) + random.gauss(0, 0.05)
        self._log_pressure[channel] = log_pressure
        return 0, float(f"{math.pow(10, log_pressure):.4e}")

    def read_gauge(self, gauge):
        status, pressure = self.read_channel(gauge.channel)
        return {"pressure": pressure, "status": status, "comm_ok": True}

    def sensor_on(self, channel):
        self._log_pressure.setdefault(channel, 0.0)

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
