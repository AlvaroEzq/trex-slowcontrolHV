import serial
import time


class ArduinoReader:
    def __init__(self, port, baudrate=9600, timeout=2):
        self.name = "ArduinoReader"
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def open(self):
        if self.ser is None or not self.ser.is_open:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)
            self.ser.reset_input_buffer()

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _read_line(self):
        line = self.ser.readline().decode(errors='ignore').strip()
        if line:
            try:
                s1, s2 = line.split(',')
                return int(s1), int(s2)
            except:
                return None
        return None

    def get_signal1(self):
        start = time.time()
        while time.time() - start < self.timeout:
            data = self._read_line()
            if data:
                return data[0]
        return None

    def get_signal2(self):
        start = time.time()
        while time.time() - start < self.timeout:
            data = self._read_line()
            if data:
                return data[1]
        return None
    
    def get_signal(self, signal_number):
        if signal_number not in [1, 2]:
            print("Invalid signal number. Use 1 or 2.")
            return None
        start = time.time()
        while time.time() - start < self.timeout:
            data = self._read_line()
            if data:
                return data[signal_number - 1]
        return None

    def get_both(self):
        start = time.time()
        while time.time() - start < self.timeout:
            data = self._read_line()
            if data:
                return data
        return None

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Arduino Serial Reader")
    parser.add_argument("--port", type=str, required=True, help="Serial port to connect to (e.g., COM3 or /dev/ttyUSB0)")
    args = parser.parse_args()

    with ArduinoReader(port=args.port) as reader:
        while True:
            signal1 = reader.get_signal1()
            signal2 = reader.get_signal2()
            if signal1 is not None and signal2 is not None:
                print(f"Signal 1: {signal1}, Signal 2: {signal2}")
            else:
                print("No data received.")
            time.sleep(1)