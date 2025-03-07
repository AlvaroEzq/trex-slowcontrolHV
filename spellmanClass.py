import socket

class Spellman:
    STX = '\x02'  # Start of Text character
    ETX = '\x03'  # End of Text character
    SUCCESS = '\x24'  # Character $
    V_MAX = 50000  # 50,000 V max spellman
    V_COEF = V_MAX / 4095
    I_MAX = 0.6  # 0.6 mA max spellman
    I_COEF = I_MAX / 4095

    def __init__(self, host='192.168.17.1', port=50001):
        self.server_host = host
        self.server_port = port
        self.name = 'Spellman SL30'
        self._vset = None
        self._iset = None
        self._vmon = None
        self._imon = None
        self._stat = None

    def send_recv(self, message, tOp=0, tOut=1):
        """ Send a message and wait for the response. """
        msg = message
        if isinstance(message, str):
            message = message.encode('ascii')

        try:
            so = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            so.settimeout(tOut)
            so.connect((self.server_host, self.server_port))
            so.sendall(message)
            so.shutdown(socket.SHUT_WR)
            so.settimeout(tOut + tOp)
            resp = b''
            while True:
                chunk = so.recv(1024)
                if not chunk:
                    break
                resp += chunk
                if b'\x03' in resp:
                    break
        except Exception as e:
            #print(f"Unexpected error with message {msg}: {e}")
            so.close()
            raise
        finally:
            so.close()
        return resp.decode('ascii')

    def build_message(self, cmd, arg=None):
        """ Returns a formatted Spellman message str. """
        if arg is None:
            return f"{self.STX}{cmd},,{self.ETX}"
        else:
            return f"{self.STX}{cmd},{arg},{self.ETX}"

    # Properties
    @property
    def vset(self):
        if self._vset is None:
            self._vset = self.get_vset()
        return self._vset

    @vset.setter
    def vset(self, voltage_V):
        self.set_vset(voltage_V)
        self._vset = voltage_V

    @property
    def iset(self):
        if self._iset is None:
            self._iset = self.get_iset()
        return self._iset

    @iset.setter
    def iset(self, current_mA):
        self.set_iset(current_mA)
        self._iset = current_mA

    @property
    def vmon(self):
        return self.get_vmon()

    @property
    def imon(self):
        return self.get_imon()

    @property
    def stat(self):
        return self.get_status()
    
    @property
    def on(self):
        return self.get_status()['HV']

    @property
    def remote(self):
        return self.get_status()['REMOTE']

    # Methods for interacting with the hardware
    def get_vset(self):
        """Request voltage setpoint."""
        ans = self.request_DAC(0)
        if ans == '':
            return -1
        return int(ans[1]) * self.V_COEF

    def set_vset(self, voltage_V):
        """Set voltage setpoint."""
        voltage = int(voltage_V / self.V_COEF)
        return self.set_DAC(0, voltage)

    def get_iset(self):
        """Request current setpoint."""
        ans = self.request_DAC(1)
        if ans == '':
            return -1
        return int(ans[1]) * self.I_COEF

    def set_iset(self, current_mA):
        """Set current setpoint."""
        current = int(current_mA / self.I_COEF)
        return self.set_DAC(1, current)

    def get_vmon(self):
        """Request voltage monitor."""
        ans = self.analog()
        if ans == '':
            return -1
        return int(ans[3]) * self.V_COEF

    def get_imon(self):
        """Request current monitor."""
        ans = self.analog()
        if ans == '':
            return -1
        return int(ans[4]) * self.I_COEF

    def get_status(self):
        """Get system and status information."""
        stat = self.status_parsed()
        stat.update(self.system_parsed())
        return stat

    # Methods for specific commands
    def set_DAC(self, i, n):
        """Set digital analog converter."""
        cmd = 10 + i
        command_message = self.build_message(cmd, n)
        try:
            ans = self.send_recv(command_message)
            return ans
        except Exception:
            return ''

    def request_DAC(self, i):
        """Request digital analog converter."""
        cmd = 14 + i
        command_message = self.build_message(cmd)
        try:
            ans = self.send_recv(command_message).strip(self.STX + self.ETX + ',').split(',')
            return ans[0], ans[1]
        except Exception:
            return ''

    def analog(self):
        """Request analog inputs."""
        cmd = 20
        command_message = self.build_message(cmd)
        try:
            ans = self.send_recv(command_message).strip(self.STX + self.ETX + ',').split(',')
            return ans[0], ans[1], ans[2], ans[3], ans[4], ans[5], ans[6], ans[7]
        except Exception:
            return ''

    def system(self):
        """Request system status."""
        cmd = 22
        command_message = self.build_message(cmd)
        try:
            ans = self.send_recv(command_message).strip(self.STX + self.ETX + ',').split(',')
            return ans[0], ans[1], ans[2], ans[3]
        except Exception:
            return ''

    def status(self):
        """Request digital input status."""
        cmd = 76
        command_message = self.build_message(cmd)
        try:
            ans = self.send_recv(command_message).strip(self.STX + self.ETX + ',').split(',')
            return ans[0], ans[1], ans[2], ans[3], ans[4], ans[5], ans[6], ans[7], ans[8]
        except Exception:
            return ''

    def system_parsed(self):
        ans = self.system()
        status = {}
        try:
            status['HV'] = bool(int(ans[1]))
            status['ILK'] = bool(int(ans[2]))
            status['FAULT'] = bool(int(ans[3]))
        except IndexError:
            status['HV'] = '??'
            status['ILK'] = '??'
            status['FAULT'] = '??'
        return status

    def status_parsed(self):
        ans = self.status()
        stat = {}
        try:
            stat['SYSFAULT'] = bool(int(ans[1])) # Fault
            stat['SYSILK'] = bool(int(ans[2])) # Interlock
            stat['REMOTE'] = bool(int(ans[3])) # Remote
            stat['SYSHV'] = bool(int(ans[4])) # High voltage
            stat['HC'] = bool(int(ans[5])) # High current
            stat['REG'] = bool(int(ans[6])) # Regulation error
            stat['ARC'] = bool(int(ans[7])) # Arc
            stat['OT'] = bool(int(ans[8])) # Over temperature
        except IndexError:
            stat['REMOTE'] = '??'
            stat['ARC'] = '??'
        return stat

    def turn_remote_on(self):
        '''Turn on remote mode
        return a tupla with command code and error code ($=>ok)'''
        cmd = 85
        arg = 1
        command_message = self.build_message(cmd,arg)
        try:
            ans = self.send_recv(command_message).strip(self.STX+self.ETX+',').split(',')
            return ans[0],ans[1]
        except Exception:
            return ''

    def turn_remote_off(self):
        '''Turn off remote mode
        return a tupla with command code and error code ($=>ok)'''
        cmd = 85
        arg = 0
        command_message = self.build_message(cmd,arg)
        try:
            ans = self.send_recv(command_message).strip(self.STX+self.ETX+',').split(',')
            return ans[0],ans[1]
        except Exception:
            return ''

    def turn_hv_on(self):
        '''Turn on high voltage
        return a tupla with command code and error code ($=>ok)'''
        cmd = 99
        arg = 1
        command_message = self.build_message(cmd,arg)
        try:
            ans = self.send_recv(command_message).strip(self.STX+self.ETX+',').split(',')
            return ans[0],ans[1]
        except Exception:
            return ''

    def turn_hv_off(self):
        '''Turn off high voltage
        return a tupla with command code and error code ($=>ok)'''
        cmd = 99
        arg = 0
        command_message = self.build_message(cmd,arg)
        try:
            ans = self.send_recv(command_message).strip(self.STX+self.ETX+',').split(',')
            return ans[0],ans[1]
        except Exception:
            return ''

    def turn_on(self):
        return self.turn_hv_on()

    def turn_off(self):
        return self.turn_hv_off()
