import socket

# The two Raspberry Pis where the bridge servers of the old slow control run
# (one systemd service per device, see servers/*.py and services/*.service there):
# - gas panel: Bronkhorsts P, Q and M (ports 50002-50004) and the gas Arduino (50000)
# - vacuum and electronics: MaxiGauge (50001) and the electronics Arduino (50000)
GAS_PANEL_HOST = "192.168.15.100"
VACUUM_ELECTRONICS_HOST = "192.168.15.101"


class BridgeError(ConnectionError):
    """The bridge server answered, but reports that it could not talk to the device."""


class BridgeClient:
    """
    Client of the TCP-to-serial bridge servers running on the Raspberry Pis of the
    gas panel (servers/*.py of the old slow control, one systemd service per device).

    Each server accepts one TCP connection per request: it reads the request until
    its end-of-message byte, forwards it to the serial port, sends back the device
    answer and closes the connection. So a new socket is opened for every message,
    exactly as the old slow control did (slowcontrol/socketClient.py).

    The framing of the messages (':' ... '\\r\\n' for the Bronkhorsts, STX ... ETX
    for the Arduinos and the MaxiGauge) is the job of each device class, this only
    moves bytes.
    """

    def __init__(self, host, port, timeout=2, name=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.name = name if name is not None else f"Bridge {host}:{port}"

    def send_recv(self, message: bytes) -> bytes:
        """
        Send a message to the bridge and return its whole answer.

        Raises ConnectionError if the server cannot be reached or does not answer,
        and BridgeError (a ConnectionError too) if the server reports that the
        serial link with the device is down or the device did not answer.
        """
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(message)
                # tell the server the request is complete, it answers once it has it
                sock.shutdown(socket.SHUT_WR)
                chunks = []
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
        except OSError as e: # includes socket.timeout and ConnectionRefusedError
            raise ConnectionError(f"{self.name}: {e}") from e

        answer = b"".join(chunks)
        if not answer:
            # the servers close without answering when the serial read times out
            raise BridgeError(f"{self.name}: empty answer to {message!r}")
        if b"error" in answer:
            # 'error' when the device did not answer properly, 'error,serial_down'
            # when the server has lost the serial port (it reconnects on its own)
            raise BridgeError(f"{self.name}: server answered {answer!r} to {message!r}")
        return answer

    # There is no persistent connection to open or close, but the device classes of
    # this package are used as context managers, so keep the same interface.
    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
