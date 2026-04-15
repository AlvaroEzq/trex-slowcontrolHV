import pyvisa

class BGA244:
    """A Python class to interface with the Stanford Research Systems BGA244 Binary Gas Analyzer
    via USB-B using pyVISA."""

    def __init__(self, resource_name):
        """Initialize the connection manager (but don't open it yet)."""
        self.rm = pyvisa.ResourceManager()
        self.resource_name = resource_name
        self.instrument = None
        self.name = "BGA244"

    def connect(self, timeout= 1000):
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

    # Add commands
    
    def get_ratio(self, primary_gas=True, unit: str = '%'):
        """
        Query the Binary Gas Ratio of Gas (page 165).
        
        Args:
            unit (str): Unit for the measurement ('%', 'ppm' or 'Frac').

        Returns:
            float: The mole fraction of the primary gas in the mixture.
        """
        gas_id = '1' if primary_gas else '2'
        response = self.query(f"RATO?{gas_id}{unit}")
        try:
            value = float(response)
            return value
        except ValueError:
            #raise ValueError(f"Invalid mole fraction response: {response}")
            return response


if __name__ == "__main__":
    # Example usage
    rm = pyvisa.ResourceManager()
    print(rm.list_resources())
    """
    with RigolPowerSupply('USB0::0x1AB1::0x0E11::DS1ZA123456789::INSTR') as ps:
        print(ps.query('*IDN?'))
        print(ps.get_ratio())
    """