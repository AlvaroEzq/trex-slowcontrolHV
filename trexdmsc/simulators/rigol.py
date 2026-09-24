import random


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
