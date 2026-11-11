import random
import time


class ArduinoIOSimulator:
    """
    Simulator of an Arduino of the slow control (trexdm_serial firmware). It takes the
    same ArduinoIOConfig objects as the real device (see devices/arduinoio.py), but it
    is not imported from there so that the simulators stay independent of the device
    modules.

    The analog inputs random walk around a nominal value, by default at 35% of their
    calibration range (e.g. 18 C for the -40 to 125 C transmitters), or the one given
    in 'nominal_values' ({channel name: value}), with rare excursions of the
    counts (probability 'excursion_probability' per read). The outputs keep the state
    they are set to, and the watchdog of the firmware is simulated too: with no
    command for 'watchdog_timeout' seconds all the pins go LOW.
    """

    def __init__(self, config, nominal_values=None, watchdog_timeout=1.0,
                 excursion_probability=0.002, failure_probability=0.01):
        self.config = config
        self.name = f"{config.name} SIMULATOR"
        self.watchdog_timeout = watchdog_timeout
        self.excursion_probability = excursion_probability
        self.failure_probability = failure_probability
        nominal_values = nominal_values or {}
        self._nominal = {}
        for channel in config.analog_channels:
            x0, y0, x1, y1 = channel.calibration
            value = nominal_values.get(channel.name, y0 + 0.35 * (y1 - y0))
            self._nominal[channel.input] = int(x0 + (value - y0) * (x1 - x0) / (y1 - y0))
        self._counts = dict(self._nominal)
        self._high = {output.name: False for output in config.outputs} # pins LOW at power up
        self._last_command = time.monotonic()

    def _command(self):
        now = time.monotonic()
        if now - self._last_command > self.watchdog_timeout:
            for name in self._high:
                self._high[name] = False
        self._last_command = now
        if random.random() < self.failure_probability:
            raise ConnectionError(f"{self.name}: simulated communication failure")

    def read_analog(self, input):
        self._command()
        counts = self._counts.get(input, 0)
        if random.random() < self.excursion_probability:
            counts += random.choice((-1, 1)) * random.randint(150, 300)
        else:
            counts += random.randint(-2, 2) + int(0.1 * (self._nominal.get(input, 0) - counts))
        self._counts[input] = min(max(counts, 0), 1023)
        return self._counts[input]

    def read_channel(self, channel):
        counts = self.read_analog(channel.input)
        return {"value": channel.to_value(counts), "counts": counts}

    def set_output(self, output, on):
        self._command()
        self._high[output.name] = bool(on) != output.inverse

    def get_output(self, output):
        self._command()
        return self._high[output.name] != output.inverse

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
