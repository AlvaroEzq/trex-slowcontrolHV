import random


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
