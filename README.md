# Gateway to Caen: Tactical Command

A dependency-free **Tkinter tactical RTS prototype** with a Windows 95 command interface, procedural battlefields, persistent game saves, and a neural commander that learns across battles and sessions.

> This is an original clean-room project inspired by the broad tactical-command genre. It does not contain proprietary Close Combat code, artwork, maps, audio, scenarios, or data, and it is not affiliated with the original game's publishers or developers.

## Features

- Windows 95-inspired interface with raised panels, menu bar, toolbar, status bar, main tabs, and sub-tabs.
- Procedural 26×17 tactical maps with roads, woods, hedgerows, villages, mud, and three capturable objectives.
- Allied and Axis formations including rifle, support, scout, mortar, and armour units.
- Real-time movement, ammunition use, terrain cover, morale, suppression, casualties, objective capture, and battle scoring.
- Select units on the tactical map or in the roster; right-click to issue movement orders.
- Orders include Hold, Advance, Defend, Assault, Flank, and Retreat.
- Enemy neural commander makes a tactical decision every **2 simulated seconds**.
- Optional Allied AI Commander mode lets the same learning system command the player side.
- Neural Q-network implemented with the Python standard library—no NumPy or machine-learning package required.
- Neural weights and lifetime statistics are silently saved every **10 seconds**.
- Game state is silently autosaved every **5 seconds**.
- The autosave and neural brain are loaded automatically on startup.
- Atomic temporary-file replacement reduces save corruption risk.

## Run on Windows

1. Install Python 3 from python.org and keep Tcl/Tk enabled during installation.
2. Double-click `run_game.bat`.

Or run from a terminal:

```powershell
py -3 main.py
```

There are no third-party dependencies.

## Controls

- **Left-click:** select a unit.
- **Shift + left-click:** add or remove a unit from the current selection.
- **Right-click:** move selected Allied units to that grid location.
- **Toolbar / Command tab:** set the selected units' orders.
- **Allied AI Commander:** allow the neural commander to control both sides.

## Persistent Data

On Windows, data is stored in:

```text
%APPDATA%\GatewayToCaen\
```

Files:

- `autosave.json` — current battle state, written every 5 seconds.
- `tactical_brain.json` — neural weights and learning statistics, written every 10 seconds.
- `settings.json` — interface and simulation settings.

Starting a new battle preserves the neural brain. Closing the application also performs a final game, brain, and settings save.

## Neural Commander

The AI uses a `10 → 18 → 5` neural Q-network. Inputs represent unit strength, morale, ammunition, suppression, enemy distance, objective distance, nearby friendly and enemy density, terrain cover, and map progress.

Its five actions are Advance, Flank, Hold, Retreat, and Assault. Training rewards account for casualties inflicted and suffered, objective progress, cover use, retreat discipline, and battle results.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```

## Project Layout

```text
main.py                         Application entry point
run_game.bat                    Windows launcher
gateway_to_caen/ui.py           Tkinter Windows 95 interface
gateway_to_caen/simulation.py   Tactical simulation and battle state
gateway_to_caen/neural.py       Persistent neural Q-network
gateway_to_caen/persistence.py  Atomic JSON persistence
tests/                          Neural and simulation tests
```
