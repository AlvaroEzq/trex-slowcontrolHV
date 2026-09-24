import random


class BronkhorstSimulator:
    """
    Simulator of a Bronkhorst of the gas panel. It takes the same BronkhorstConfig
    objects as the real device (see devices/bronkhorst.py), but it is not imported
    from there so that the simulators stay independent of the device modules.

    The measurement of a controller relaxes towards its setpoint. A meter follows the
    measurement of 'source' (another simulator, e.g. the flow controller in series
    with it) if given, or random walks otherwise.
    """

    def __init__(self, config, source=None, noise=0.005, failure_probability=0.01):
        self.config = config
        self.name = f"{config.name} SIMULATOR"
        self.source = source
        self.noise = noise * config.full_scale
        self.failure_probability = failure_probability
        self._setpoint = config.full_scale * (0.15 if config.controller else 0.0)
        self._measure = self._setpoint if source is None else source._measure

    def _maybe_fail(self):
        if random.random() < self.failure_probability:
            raise ConnectionError(f"{self.name}: simulated communication failure")

    def _step(self):
        if self.config.controller:
            target = self._setpoint
        elif self.source is not None:
            target = self.source._measure
        else:
            target = self._measure
        self._measure += 0.3 * (target - self._measure) + random.gauss(0, self.noise)
        self._measure = min(max(self._measure, 0.0), 1.31 * self.config.full_scale)

    def read_measure(self):
        self._maybe_fail()
        self._step()
        return round(self._measure, 3)

    def read_setpoint(self):
        self._maybe_fail()
        return self._setpoint

    def set_setpoint(self, value):
        if not self.config.controller:
            raise ValueError(f"{self.name} is a meter, it has no setpoint")
        if not self.config.setpoint_min <= value <= self.config.max_setpoint:
            raise ValueError(f"{self.name}: setpoint {value} {self.config.unit} out of"
                             f" [{self.config.setpoint_min}, {self.config.max_setpoint}]")
        self._maybe_fail()
        self._setpoint = value

    def read(self):
        values = {"measure": self.read_measure()}
        if self.config.controller:
            values["setpoint"] = self.read_setpoint()
        return values

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
