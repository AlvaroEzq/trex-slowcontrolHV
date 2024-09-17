import datetime as dt
import os

LOG_DIR = "logs"

class State:
    def __init__(self, vmon=0, imon=0, stat=None):
        if stat is None:
            stat = {}
        self.time = dt.datetime.now()
        self.vmon = imon
        self.imon = vmon
        self.stat = stat
    
    def set_state(self, vmon, imon, stat):
        self.time = dt.datetime.now()
        self.vmon = vmon
        self.imon = imon
        self.stat = stat

    def __str__(self):
        return "vmon: {:.2f}V, imon: {:.2f}uA, stat: {}".format(self.vmon, self.imon, self.stat)

    def print_state(self):
        print("Time:", self.time.strftime("%Y-%m-%d %H:%M:%S"))
        print("vmon: {:.2f}V, imon: {:.2f}uA, stat: {}".format(self.vmon, self.imon, self.stat))

    def write_to_file(self, filename, delimiter=' ', precision_vmon=1, precision_imon=3):
        if not os.path.isfile(filename):
            try:
                # create the file if it does not exist
                with open(filename, 'w') as file:
                    file.write('Time' + delimiter + 'Vmon(V)' + delimiter + 'Imon(uA)' + '\n')
                print("Writing to new file:", filename)
            except:
                print("Invalid file or directory:", filename)

        with open(filename, 'a') as file:
            file.write(f"{self.time.strftime('%Y-%m-%d %H:%M:%S')}{delimiter}{self.vmon:.{precision_vmon}f}{delimiter}{self.imon:.{precision_imon}f}\n")

    def assign(self, other):
        self.time = other.time
        self.vmon = other.vmon
        self.imon = other.imon
        self.stat = other.stat

    def __eq__(self, other):
        return all([self.time == other.time, self.vmon == other.vmon, self.imon == other.imon, self.stat == other.stat])
    
    def __ne__(self, other):
        return not self.__eq__(other)

class ChannelState:
    def __init__(self, name="", ch=None, diff_vmon=0.5, diff_imon=0.01, precision_vmon=1, precision_imon=3):
        self.channel = ch
        self.channel_name = name

        self.current = State()
        self.previous = State()
        self.last_saved = State()

        self.diff_vmon = diff_vmon
        self.diff_imon = diff_imon
        self.precision_vmon = precision_vmon
        self.precision_imon = precision_imon

        self.filename = LOG_DIR + "/Log_" + self.channel_name.replace(" ", "") + ".dat"

    def __str__(self):
        return self.channel_name + ": " + str(self.current)

    def set_state(self, state):
        '''
        if not state: # avoid using this as it should use the device lock
            time = dt.datetime.now()
            vmon = self.channel.vmon
            imon = self.channel.imon
            stat = self.channel.stat
            state = State(time, vmon, imon, stat)
        '''
        self.previous.assign(self.current)
        self.current.assign(state)

    def set_state(self, vmon, imon, stat=None):
        if stat is None:
            stat = {}
        self.previous.assign(self.current)
        self.current.set_state(vmon, imon, stat)

    def print(self):
        print(self.channel_name)
        print("Time:", self.current.time.strftime("%Y-%m-%d %H:%M:%S"))
        print(self.current)

    def is_different(self):
        return (abs(self.current.vmon - self.last_saved.vmon) >= self.diff_vmon) or (abs(self.current.imon - self.last_saved.imon) >= self.diff_imon)

    def save_state(self, force=False, save_previous=True):
        if self.is_different() or force:
            if self.last_saved != self.previous and save_previous:
                self.previous.write_to_file(self.filename, precision_vmon=self.precision_vmon, precision_imon=self.precision_imon)
            self.current.write_to_file(self.filename, precision_vmon=self.precision_vmon, precision_imon=self.precision_imon)
            self.last_saved.assign(self.current)


