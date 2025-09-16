import pyvisa

class RigolPowerSupply:
    def __init__(self, resource_name, name="Rigol"):
        """Initialize the connection manager (but don't open it yet)."""
        self.rm = pyvisa.ResourceManager()
        self.resource_name = resource_name
        self.instrument = None
        self.name = name

    def connect(self, timeout=5000):
        """Open the connection to the power supply."""
        self.instrument = self.rm.open_resource(self.resource_name)
        self.instrument.timeout = timeout

    def disconnect(self):
        """Close the connection to the power supply."""
        if self.instrument:
            self.instrument.close()
            self.instrument = None
    
    def open(self):
        """Open the connection to the power supply. (Alias for connect)"""
        self.connect()

    def close(self):
        """Close the connection to the power supply. (Alias for disconnect)"""
        self.disconnect()

    def __enter__(self):
        """Open the connection when entering the context."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the connection when exiting the context."""
        self.disconnect()

    def write(self, command):
        """Send a SCPI command to the power supply."""
        if self.instrument:
            self.instrument.write(command)
        else:
            raise ConnectionError("Instrument not connected.")

    def query(self, command):
        """Send a SCPI command and return the response."""
        if self.instrument:
            return self.instrument.query(command)
        else:
            raise ConnectionError("Instrument not connected.")

    # Add additional functionality
    def turn_on_channel(self, channel_number):
        """Turn on the output for a channel."""
        self.write(f":OUTP CH{channel_number},1")
    
    def turn_off_channel(self, channel_number):
        """Turn off the output for a channel."""
        self.write(f":OUTP CH{channel_number},0")

    def enable_output(self, channel_number):
        """Enable output for a channel."""
        self.turn_on_channel(channel_number)

    def disable_output(self, channel_number):
        """Disable output for a channel."""
        self.turn_off_channel(channel_number)

    def get_output_state(self, channel_number):
        """Get the output state of a channel (enabled/disabled)."""
        return self.query(f":OUTP? CH{channel_number}").strip()

    def set_voltage_protection(self, channel_number, voltage):
        """Set the over-voltage protection (OVP) limit for a channel."""
        self.write(f":OUTP:OVP:VAL CH{channel_number},{voltage}")
        self.write(f":OUTP:OVP CH{channel_number},1")  # Enable OVP

    def set_current_protection(self, channel_number, current):
        """Set the over-current protection (OCP) limit for a channel."""
        self.write(f":OUTP:OCP:VAL CH{channel_number},{current}")
        self.write(f":OUTP:OCP CH{channel_number},1")  # Enable OCP

    def measure_voltage(self, channel_number):
        """Measure the voltage on a channel."""
        return self.query(f":MEAS:VOLT? CH{channel_number}")

    def measure_current(self, channel_number):
        """Measure the current on a channel."""
        return self.query(f":MEAS:CURR? CH{channel_number}")

    def measure_all(self, channel_number):
        """Measure voltage, current, and power on a channel."""
        raw = self.query(f":MEAS:ALL? CH{channel_number}") # "e.g. '3.3,0.5,1.65'
        values = raw.replace('\r\n','').split(',')
        measurements = {'voltage': float(values[0]),
                        'current': float(values[1]),
                        'power': float(values[2])}
        return measurements

    def get_set_voltage(self, channel_number):
        """Get the set voltage for a channel."""
        return self.query(f":SOUR{channel_number}:VOLT?")

    def get_set_current(self, channel_number):
        """Get the set current for a channel."""
        return self.query(f":SOUR{channel_number}:CURR?")

