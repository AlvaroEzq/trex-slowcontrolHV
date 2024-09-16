# TREX-DM Slow Control HV

This repository contains software for remote control and monitoring of high voltage (HV) power supplies, primarily used for the TREX-DM experiment.

## Features

- Control of HV devices (CAEN and Spellman).
- Main graphical interface with integrated control for multiple devices.
- Individual GUIs for each device.
- HV device simulator for testing without hardware.

## Requirements

- Python 3.x
- Additional libraries listed in `requirements.txt` (if available).

## Project Structure

- `trex_HV_gui.py`: **Main GUI** that contains individual interfaces for CAEN and Spellman HV devices, as well as multi-device control.
- `caengui.py`: GUI for CAEN HV devices.
- `spellmangui.py`: GUI for Spellman HV devices.
- `caen_simulator.py`: CAEN device simulator.
- `spellmanClass.py`: Class for managing the Spellman HV supply.
- `tooltip.py`: Tooltip handler.
- `check.py`: System checks.

## Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/AlvaroEzq/trex-slowcontrolHV.git
   ```
2. Run the main GUI
   ```bash
   python3 trex_HV_gui.py
   ```
   Or run it with the simulator for testing (so the hardware is not needed)
   ```bash
   python3 trex_HV_gui.py --test
   ```
   You can also run the individual devices GUI independently. For example,
   ```bash
   python3 caen_gui.py --port /dev/ttyUSB0
   ```
