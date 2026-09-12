# TREX-DM Slow Control HV

This repository contains software for remote control and monitoring of high voltage (HV) power supplies, primarily used for the TREX-DM experiment.

![CAEN HV power supply GUI.](docs/maingui.png)

## Terminology

Two different things in this project could both be called "logging", so they are named apart:

- **logging** — human-readable messages and alarms, handled with the python `logging` module
  ([logger.py](logger.py)). Goes to the terminal pane, `logs/*.log`, and the Slack/Mattermost webhooks.
- **recording** — measured channel values written to data files ([channel.py](channel.py)).
  Controlled by the `recording_enabled` option ("Record values to file" in the *Config → Advanced
  options* dialog).

## Features
- Graphical User Interface (GUI) for individual and multiple HV power supply devices. Including:
   - Security checks for individual and multiple devices.
   - Recording of voltage and current monitor values of the channels of each device to file.
   - Automatic multidevice raising of voltages and turning off following the standard protocol (raising or lowering all channels involved voltages simultaneously by steps).
   - Trip recovery system to automatically detect, handle and recover a trip. It uses the multidevice raising of voltages to recover a trip. Also, a configurable cooldown time is applied before recovering the trip.
   - Alert message to slack/mattermost webhook (to do so, copy your slack/mattermost webhook in the global variable SLACK/MATTERMOST_WEBHOOK_URL of [logger.py](logger.py)). You can select the logging level os the slack messages in the config menu bar. These are the logging levels logic:
      * CRITICAL: unexpected error happens which require the user to fix.
      * ERROR: expected error happens which require the users attention.
      * WARNING: expected event as trips.
      * INFO: information on the normal functioning of the program, including trip recovery messages when a trip is detected and recovered successfully.
      * DEBUG: debugging information.

      It is recommended to set the slack/mattermost logging level to warning if you want to receive messages when trips happen or error if you want to ignore the messages of trips.
   - DAQ monitoring through the [feminos-daq](https://github.com/rest-for-physics/feminos-daq) or [femdaq](https://github.com/juanangp/femdaq) prometheus metrics. As the current DAQ computer is different from the slow-control PC, an ssh connection is established. Make sure to have the necessary ssh key-pair user credentials installed (on the DAQ PC) for the SSH key-based authentication.
   - Auto and manual button to add the current run information (run number, run type, metadata in the output file name, voltages and electronic threshold) to the Google Sheet run list. To configure the connection to the Google Sheet you should change the global variables at `utils.py`. Make sure to have the appropiate google service account credentials (json file) in the root directory.
- Monitoring of the sensor and alarm safety system for the use of flammable gas (isobutane): the gas sensors connected to an MX32v2 controller and the digital alarm signals of the safety system read by an Arduino. Every alarm raised or cleared is logged (the raised ones as critical records, so they reach the slack/mattermost webhook).
- CAEN, Spellman SL30, Rigol, MX32v2 and Arduino simulators for testing without hardware.

## Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/AlvaroEzq/trex-slowcontrolHV.git
   ```
2. Run the main GUI (all the subsystems, with the sidebar to switch between them)
   ```bash
   python3 supergui.py
   ```
   Or run it with the simulators for testing (so the hardware is not needed)
   ```bash
   python3 supergui.py --test
   ```
   You can also run a single subsystem independently. For example, the HV one:
   ```bash
   python3 multiHVgui.py
   python3 multiHVgui.py --test
   python3 multiflammablegasgui.py
   python3 multiflammablegasgui.py --test
   ```
   Or even the GUI of an individual device. For example,
   ```bash
   python3 caengui.py --port /dev/ttyUSB0
   ```

## Recorded data

While the GUI runs, the monitored values of every channel are recorded to plain text
files, one per channel per day:

```
data/2026/09/11/20260911_gemtop.dat
   # Time vmon[V] imon[uA]
   2026-09-11T13:05:39 100.1 0.010
   2026-09-11T13:05:45 99.1 0.010
```

Spaces are removed from the channel name (`mesh right` becomes `meshright`). A row is
only written when a value moves past its threshold, so the sampling is irregular. If
the recorded magnitudes change (different units, or a different set of values saved),
the day continues in `20260911_gemtop_1.dat` rather than filing new rows under a stale
header.

The root is the `data` directory next to the code, so it does not depend on where you
launch from. Override it with `--data-dir` or the `TREX_HV_DATA` environment variable;
the GUI prints the directory it settled on at startup. Recording can be turned off
per device with `record=False`, or at runtime in *Config → Advanced options*.

The header is commented and the timestamp is a single token, so the files load with no
preparation:

```bash
gnuplot -e 'set xdata time; set timefmt "%Y-%m-%dT%H:%M:%S"; plot "20260911_gemtop.dat" using 1:2'
```
```python
import numpy as np
vmon, imon = np.loadtxt("20260911_gemtop.dat", usecols=(1, 2), unpack=True)
```

Files recorded before September 2026 have an uncommented header and a space between the
date and the time, so those two examples need `skiprows=1` and a different `timefmt`.
`hvdata.py` below reads both layouts, including a single file that spans the change.

### Reading a time range

[hvdata.py](hvdata.py) gathers the day files across a range, including the `_1`/`_2`
siblings, and hands back a single table:

```bash
python3 hvdata.py list                                   # channels present on disk
python3 hvdata.py info -c "gem top" --from -7d           # files, rows, units, gaps
python3 hvdata.py dump -c "gem top" --from -7d --epoch   # ready for gnuplot or awk
python3 hvdata.py dump -c cathode --from 2026-09-01 --to 2026-09-11 --csv -o out.csv
```

```python
import hvdata
df = hvdata.read_channel("cathode", "2026-09-01", "2026-09-11")  # pandas DataFrame
df["vmon"].plot()
hvdata.units_of(df)                          # {'vmon': 'V', 'imon': 'mA'}
t, values, names = hvdata.to_numpy(df)       # unix seconds + a 2-D array, for ROOT
```

Dates accept ISO (`2026-09-11`, `2026-09-11 13:00`), the words `now`/`today`/`yesterday`,
and offsets like `-7d` or `-12h`. A bare `--to` date includes the whole of that day. If
sibling files disagree on units, they are rescaled to the units of the first file and
each conversion is reported; `--units raise` refuses to guess and `--units keep` leaves
the values alone and tags each row with the file it came from.

## Requirements

- Python 3.x
- tkinter (for installation check [this](https://stackoverflow.com/a/74607246)).
- Additional python libraries listed in `requirements.txt`.

## GUI architecture

The GUIs are organized in three levels, and every level can be used on its own:

```text
SuperGUI                     (sidebar + navigation, owns the Tk root)
├── HVGUI (MultiDeviceGUI)   (a subsystem: CAEN + Spellman + DAQ metrics + ...)
│   ├── CaenHVPSGUI (DeviceGUI)
│   ├── SpellmanFrame (DeviceGUI)
│   └── ...
└── FlammableGasGUI (MultiDeviceGUI)
    ├── MX32v2GUI (DeviceGUI)
    └── ArduinoGUI (DeviceGUI)
```

Two rules define the architecture:

1. **Hardware acquisition and GUI rendering are separated.** Each `DeviceGUI` runs its
   own background read loop that calls `read_values()` (hardware communication +
   internal state update + logging, never Tk widgets), while `update_gui()` runs in
   the Tk main thread and only reads the state to update the widgets (never blocking
   hardware communication). They communicate exclusively through the `ChannelState`
   of each channel.
2. **The highest-level GUI owning a group of GUIs is responsible for their GUI
   scheduling.** This is controlled by the `auto_gui_update` argument: a GUI created
   with `auto_gui_update=True` (the default, standalone use) owns an `after()` loop
   calling its own `update_gui()` every `gui_update_time` seconds, and a GUI created
   with `auto_gui_update=False` (managed use) never schedules an `after()` callback
   and relies on its parent calling `update_gui()`.

| Object           | Standalone             | Managed by a parent |
| ---------------- | ---------------------- | ------------------- |
| `DeviceGUI`      | `auto_gui_update=True` | `False`             |
| `MultiDeviceGUI` | `auto_gui_update=True` | `False`             |
| `SuperGUI`       | N/A                    | owns the scheduler  |

So there is a single `after()` GUI update loop in the application, and in the
`SuperGUI` case only the subsystem currently displayed updates its widgets. Note
that `auto_gui_update` only controls the Tk widget updates: **the background reading
and the logging of a hidden subsystem keep running**, only its rendering is stopped.

Regarding the Tk hierarchy, `self.root` is always the actual Tk root of the
application, while `self.frame` is the widget container owned by each GUI object:

```text
Tk root
└── SuperGUI content frame
    ├── HVGUI.frame
    │   ├── CaenHVPSGUI.frame
    │   └── SpellmanFrame.frame
    └── FlammableGasGUI.frame
        ├── MX32v2GUI.frame
        └── ArduinoGUI.frame
```

Only the top level runs `mainloop()`: a `DeviceGUI` or a `MultiDeviceGUI` starts it
only when it is the standalone/top-level GUI (i.e. when no `parent_frame` is given).

## Project Structure

- GUIs modules
   - `supergui.py`: **Main GUI** that contains the different subsystems (HV, ...) and the sidebar to navigate between them. It owns the only GUI update scheduler of the application.
   - `multidevicegui.py`: Implementation of the abstract class that serves as base class for the subsystem GUIs (a group of device GUIs). Implement the `create_gui` abstract method, creating there the children `DeviceGUI`s with `auto_gui_update=False` inside `self.frame` and registering them in `self.all_guis`.
   - `multiHVgui.py`: **HV subsystem GUI** that contains individual interfaces for CAEN and Spellman HV devices, as well as multi-device control. It can be run on its own.
   - `multiflammablegasgui.py`: **Flammable gas safety subsystem GUI**, grouping the GUIs of the two devices of the isobutane sensor and alarm safety system (the MX32v2 gas sensor controller and the Arduino). It can be run on its own.
   - `multirigolgui.py`: Subsystem GUI grouping several Rigol power supplies. It can be run on its own.
   - `devicegui.py`: Implementation of the abstract class that serves as base class for the individual devices GUIs. This abstract class implements a device lock for multithreading-safe communication with the device and a command queue to keep the order of the communications to the device. Please, use the `issue_command` method (or at least acquire the device lock manually) for any function (or statement) that requires to communicate with the device to avoid spurious errors. To write the individual device GUI, define your class as a children of this base class and implement the appropiate `read_values` (for background monitoring) and `create_gui` (for the GUI layout) abstract methods for your particular case. Do not forget to call the parent class constructor (`super().__init__`) at the end of your the class constructor (`__init__`), as it will start the GUI mainloop (when used standalone) and any line written after this will not be executed (until the GUI is closed). Build the widgets of the GUI inside `self.frame` and forward the `auto_gui_update` argument to `super().__init__`. You can use the following as examples:
      - `caengui.py`: GUI for CAEN HV devices.
      - `spellmangui.py`: GUI for Spellman HV devices.
      - `rigolgui.py`: GUI for Rigol power supplies.
      - `mx32v2gui.py`: GUI for the gas sensors connected to an MX32v2 controller.
      - `arduinogui.py`: GUI for the digital alarm signals of the safety system read by an Arduino.
      - `daqmetricsgui.py`: GUI for the DAQ metrics.
   - `checkframe.py`: Implementation of the ChecksFrame class to display and manage the checks.
   - `utilsgui.py`: Implementation of GUI utility classes such as ToolTip and PrintToTextWidget.
- Device modules
   - `spellmanClass.py`: Class for managing the Spellman HV supply.
   - `rigolClass.py`: Class for managing the Rigol power supplies.
   - `mx32v2.py`: Class for managing the MX32v2 gas sensor controller (through Modbus) and the configuration of the sensors of the installation (which sensors are connected to each line and what their alarm thresholds are).
   - `arduino.py`: Class for reading the digital alarm signals of the safety system from the Arduino serial line.
   - `simulators.py`: CAEN, Spellman, Rigol, MX32v2 and Arduino device simulator classes.
- Support modules
   - `check.py`: Implementation of the checks classes.
   - `logger.py`: Logging helpers for human-readable messages and alarms: Slack, Mattermost and
     Tk-widget handlers, plus the logger configuration functions. Nothing here writes measured values.
   - `channel.py`: Implementation of the State and ChannelState classes, which hold the in-memory
     snapshots of a channel's values and record them to file.
   - `daqmetrics.py`: Implementation of MetricsFetcher and MetricsFetcherSSH to extract the prometheus metrics of the [feminos-daq](https://github.com/rest-for-physics/feminos-daq) acquisition program.
   - `utils.py`: Other useful functions. For now, it includes the necessary functions for adding rows to the Google Sheet run list.
