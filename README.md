# TREX-DM Slow Control HV

This repository contains software for remote control and monitoring of high voltage (HV) power supplies, primarily used for the TREX-DM experiment.

![CAEN HV power supply GUI.](docs/maingui.png)

## Features
- Graphical User Interface (GUI) for individual and multiple HV power supply devices. Including:
   - Security checks for individual and multiple devices.
   - Register of voltage and current monitor values of the channels of each device.
   - Automatic multidevice raising of voltages and turning off following the standard protocol (raising or lowering all channels involved voltages simultaneously by steps).
   - Trip recovery system to automatically detect, handle and recover a trip. It uses the multidevice raising of voltages to recover a trip. Also, a configurable cooldown time is applied before recovering the trip.
   - Alert message to slack/mattermost webhook (to do so, copy your slack/mattermost webhook in the global variable SLACK/MATTERMOST_WEBHOOK_URL of [trexdmsc/core/logger.py](trexdmsc/core/logger.py)). You can select the logging level os the slack messages in the config menu bar. These are the logging levels logic:
      * CRITICAL: unexpected error happens which require the user to fix.
      * ERROR: expected error happens which require the users attention.
      * WARNING: expected event as trips.
      * INFO: information on the normal functioning of the program, including trip recovery messages when a trip is detected and recovered successfully.
      * DEBUG: debugging information.

      It is recommended to set the slack/mattermost logging level to warning if you want to receive messages when trips happen or error if you want to ignore the messages of trips.
   - DAQ monitoring through the [feminos-daq](https://github.com/rest-for-physics/feminos-daq) or [femdaq](https://github.com/juanangp/femdaq) prometheus metrics. As the current DAQ computer is different from the slow-control PC, an ssh connection is established. Make sure to have the necessary ssh key-pair user credentials installed (on the DAQ PC) for the SSH key-based authentication.
   - Auto and manual button to add the current run information (run number, run type, metadata in the output file name, voltages and electronic threshold) to the Google Sheet run list. To configure the connection to the Google Sheet you should change the global variables at `trexdmsc/utils/googlesheet.py`. Make sure to have the appropiate google service account credentials (json file) in the root directory.
- Monitoring of the sensor and alarm safety system for the use of flammable gas (isobutane): the gas sensors connected to an MX32v2 controller and the digital alarm signals of the safety system read by an Arduino. Every alarm raised or cleared is logged (the raised ones as critical records, so they reach the slack/mattermost webhook).
- Monitoring and control of the gas system, ported from the old TREX-DM slow control:
   - Gas circuit: Bronkhorst pressure controller (PT41/PCV41), flow controller (FQT40/FQC40) and flow meter (QT41), with setpoint control, and the gas panel Arduino with the pressure and temperature transmitters (PT40, TT40, PT32, TT32, PT30, TT30), the pump relay and the pneumatic valve V40-V46.
   - Vacuum: the 6 gauges of the Pfeiffer MaxiGauge (PT31 gas system and PT71 chamber vacuum).
   - The alarm levels of the safety checks of the old slow control (overpressure, pressure/flow above the setpoint, temperatures out of range, vacuum lost) are raised as critical records, so they reach the slack/mattermost webhook. The automatic interlock actions of the old slow control are not ported (only the alarms).
- Electronics: the relays of the electronics power supplies and the Hall current sensors, read by the electronics Arduino.
- Read-only mode (`--read-only`) for the gas and electronics subsystems, to monitor them without sending any command (e.g. while the old slow control is still in use).
- CAEN, Spellman SL30, Rigol, MX32v2, Arduino, Bronkhorst, MaxiGauge and gas/electronics Arduino simulators for testing without hardware.

## Usage

1. Clone the repository and install it (editable mode, so the code can be modified without reinstalling):
   ```bash
   git clone https://github.com/AlvaroEzq/trex-slowcontrolHV.git
   cd trex-slowcontrolHV
   pip install -e .
   ```
2. Run the main GUI (all the subsystems, with the sidebar to switch between them) from the repository root (the `logs/` directory and the `config/checks_config.toml` default are relative to the working directory)
   ```bash
   trexdm-sc
   ```
   Or run it with the simulators for testing (so the hardware is not needed)
   ```bash
   trexdm-sc --test
   ```
   You can also run a single subsystem independently. For example, the HV one:
   ```bash
   trexdm-sc-hv
   trexdm-sc-hv --test
   trexdm-sc-flammablegas
   trexdm-sc-flammablegas --test
   trexdm-sc-gas --read-only
   trexdm-sc-electronics --test
   ```
   Or even the GUI of an individual device. For example,
   ```bash
   trexdm-sc-caen --port /dev/ttyUSB0
   ```
   The available commands are `trexdm-sc`, `trexdm-sc-hv`, `trexdm-sc-flammablegas`, `trexdm-sc-gas`, `trexdm-sc-electronics`, `trexdm-sc-rigol`, `trexdm-sc-caen`, `trexdm-sc-spellman`, `trexdm-sc-rigol-device`, `trexdm-sc-mx32v2`, `trexdm-sc-arduino`, `trexdm-sc-bronkhorst`, `trexdm-sc-maxigauge`, `trexdm-sc-arduinoio` and `trexdm-sc-daqmetrics` (use `--help` to see their options). Every module with a `main()` can also be run without installing the commands, e.g. `python3 -m trexdmsc.gui.devices.caen --port /dev/ttyUSB0`.

### Gas system and electronics hardware

The Bronkhorsts, the MaxiGauge and the gas and electronics Arduinos are not connected
to the slow control PC: as in the old slow control, each of them is connected to one of
two Raspberry Pis that run a TCP-to-serial bridge server per device (the
`servers/*.py` and `services/*.service` of the old slow control). The default hosts are
`192.168.15.100` (gas panel: Bronkhorsts and gas Arduino) and `192.168.15.101` (MaxiGauge
and electronics Arduino), and can be changed with the `--gas-host`, `--vacuum-host` and
`--electronics-host` options.

The firmware of the Arduinos has a watchdog: without any command for 1 second it
drives all its outputs LOW, which switches the pump off and closes the pneumatic valve
(the electronics relays are active LOW, so they stay on). The Arduino GUIs read every
0.5 s (also in read-only mode), which keeps them alive, and warn if a read cycle gets
too close to the watchdog timeout. So stopping the slow control (without the old one
running) switches the pump off and closes the valve.

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
├── FlammableGasGUI (MultiDeviceGUI)
│   ├── MX32v2GUI (DeviceGUI)
│   └── ArduinoGUI (DeviceGUI)
├── GasGUI (MultiDeviceGUI)
│   ├── BronkhorstGUI (DeviceGUI) x3
│   ├── ArduinoIOGUI (DeviceGUI)
│   └── MaxiGaugeGUI (DeviceGUI)
└── ElectronicsGUI (MultiDeviceGUI)
    └── ArduinoIOGUI (DeviceGUI)
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

The code is organized in layers inside the `trexdmsc` package. The hardware modules never import tkinter, and the GUI modules never talk to the hardware outside `read_values()` / `issue_command()`.

```text
config/checks_config.toml   default checks configuration
logs/                       output logs (created at runtime)
trexdmsc/
├── core/                   framework support (no hardware, no GUI)
├── devices/                device API classes (hardware communication)
├── simulators/             device simulators for --test mode
├── gui/
│   ├── base/               GUI base classes and widgets
│   ├── devices/            one DeviceGUI per device
│   ├── subsystems/         MultiDeviceGUIs grouping device GUIs
│   └── supergui.py
└── utils/
```

- `trexdmsc/gui/`: GUI modules
   - `supergui.py`: **Main GUI** that contains the different subsystems (HV, ...) and the sidebar to navigate between them. It owns the only GUI update scheduler of the application.
   - `base/multidevicegui.py`: Implementation of the abstract class that serves as base class for the subsystem GUIs (a group of device GUIs). Implement the `create_gui` abstract method, creating there the children `DeviceGUI`s with `auto_gui_update=False` inside `self.frame` and registering them in `self.all_guis`.
   - `base/devicegui.py`: Implementation of the abstract class that serves as base class for the individual devices GUIs. This abstract class implements a device lock for multithreading-safe communication with the device and a command queue to keep the order of the communications to the device. Please, use the `issue_command` method (or at least acquire the device lock manually) for any function (or statement) that requires to communicate with the device to avoid spurious errors. To write the individual device GUI, define your class as a children of this base class and implement the appropiate `read_values` (for background monitoring) and `create_gui` (for the GUI layout) abstract methods for your particular case. Do not forget to call the parent class constructor (`super().__init__`) at the end of your the class constructor (`__init__`), as it will start the GUI mainloop (when used standalone) and any line written after this will not be executed (until the GUI is closed). Build the widgets of the GUI inside `self.frame` and forward the `auto_gui_update` argument to `super().__init__`.
   - `base/checkframe.py`: Implementation of the ChecksFrame class to display and manage the checks.
   - `base/widgets.py`: Implementation of GUI utility classes such as ToolTip and PrintToTextWidget.
   - `base/readfailures.py`: `ReadFailureMixin` for `DeviceGUI`s: tolerance to transient read failures (only reported once they persist) and logging of the alarm transitions (critical when raised, info when cleared).
   - `base/readonly.py`: `write_command` decorator for the `DeviceGUI` methods that write to the device, which are ignored in read-only mode.
   - `subsystems/`: subsystem GUIs, each of them can be run on its own.
      - `hv.py`: **HV subsystem GUI** that contains individual interfaces for CAEN and Spellman HV devices, as well as multi-device control.
      - `flammablegas.py`: **Flammable gas safety subsystem GUI**, grouping the GUIs of the two devices of the isobutane sensor and alarm safety system (the MX32v2 gas sensor controller and the Arduino).
      - `gas.py`: **Gas subsystem GUI**: the gas circuit (Bronkhorsts and gas panel Arduino) and the vacuum gauges (MaxiGauge).
      - `electronics.py`: **Electronics subsystem GUI**: the electronics relays and Hall current sensors (electronics Arduino).
      - `rigol.py`: Subsystem GUI grouping several Rigol power supplies.
   - `devices/`: individual device GUIs. You can use them as examples:
      - `caen.py`: GUI for CAEN HV devices.
      - `spellman.py`: GUI for Spellman HV devices.
      - `rigol.py`: GUI for Rigol power supplies.
      - `mx32v2.py`: GUI for the gas sensors connected to an MX32v2 controller.
      - `arduino.py`: GUI for the digital alarm signals of the safety system read by an Arduino.
      - `daqmetrics.py`: GUI for the DAQ metrics.
      - `bronkhorst.py`: GUI for a Bronkhorst pressure/flow controller or flow meter.
      - `maxigauge.py`: GUI for the vacuum gauges of the MaxiGauge.
      - `arduinoio.py`: GUI for an Arduino with the trexdm_serial firmware (analog sensors and relays), used for both the gas panel and the electronics Arduinos.
- `trexdmsc/devices/`: device modules (the CAEN one is the external `hvps` library)
   - `spellman.py`: Class for managing the Spellman HV supply.
   - `rigol.py`: Class for managing the Rigol power supplies.
   - `mx32v2.py`: Class for managing the MX32v2 gas sensor controller (through Modbus) and the configuration of the sensors of the installation (which sensors are connected to each line and what their alarm thresholds are).
   - `arduino.py`: Class for reading the digital alarm signals of the safety system from the Arduino serial line.
   - `bridge.py`: Client of the TCP-to-serial bridge servers of the Raspberry Pis of the gas system and electronics.
   - `bronkhorst.py`: Class for the Bronkhorst instruments (ProPar ASCII protocol) and the configuration of the three instruments of the gas panel.
   - `maxigauge.py`: Class for the Pfeiffer MaxiGauge and the configuration of its gauges.
   - `arduinoio.py`: Class for the Arduinos with the trexdm_serial firmware and the configuration of the gas panel and electronics Arduinos (sensors with their calibrations and alarms, and relays).
   - `daqmetrics.py`: Implementation of MetricsFetcher and MetricsFetcherSSH to extract the prometheus metrics of the [feminos-daq](https://github.com/rest-for-physics/feminos-daq) acquisition program.
- `trexdmsc/simulators/`: CAEN, Spellman, Rigol, MX32v2, Arduino, Bronkhorst, MaxiGauge and Arduino I/O device simulator classes (one module per device, all of them importable from `trexdmsc.simulators`).
- `trexdmsc/core/`: support modules
   - `channel.py`: Implementation of the State and ChannelState classes (with absolute and relative logging thresholds).
   - `check.py`: Implementation of the checks classes.
   - `logger.py`: Logging helper functions and classes (slack/mattermost/text widget handlers).
- `trexdmsc/utils/googlesheet.py`: Other useful functions. For now, it includes the necessary functions for adding rows to the Google Sheet run list.

### Adding a new device

1. Write the device API class in `trexdmsc/devices/` and its simulator in `trexdmsc/simulators/` (and export it in `trexdmsc/simulators/__init__.py`).
2. Write its `DeviceGUI` in `trexdmsc/gui/devices/`, with a `main()` for standalone use.
3. Add it to a subsystem in `trexdmsc/gui/subsystems/` (or create a new one and register it in `trexdmsc/gui/supergui.py`).
4. Optionally, add a console script for it in `pyproject.toml`.
