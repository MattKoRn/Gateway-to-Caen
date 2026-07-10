# Gateway to Caen: Tactical Command

A dependency-free **Tkinter tactical RTS prototype** with a Windows 95 command interface, procedural battlefields, side-aware fog of war, persistent game saves, and a neural commander that learns across maps and sessions.

> This is an original clean-room project inspired by the broad tactical-command genre. It does not contain proprietary Close Combat code, artwork, maps, audio, scenarios, or data, and it is not affiliated with the original game's publishers or developers.

## Features

- Windows 95-inspired interface with raised panels, menu bar, toolbar, status bar, main tabs, and sub-tabs.
- New saves ask whether the player will command **Allied** or **Axis** forces.
- Axis command mirrors the tactical map horizontally, keeping the player formation on the left side of the screen.
- Side-aware fog of war:
  - friendly units reveal terrain around them;
  - Scout and Armour formations have larger visual ranges;
  - rain, low cloud, and woods reduce visibility;
  - currently hidden enemies and objective ownership remain concealed;
  - previously explored terrain remains dimly visible.
- Procedural 26×17 maps with roads, woods, hedgerows, villages, mud, and three capturable objectives.
- Allied and Axis formations including rifle, support, scout, mortar, and armour units.
- Smooth accelerated movement with continuous velocity, turning, formation separation, and roughly 30 FPS battlefield animation.
- Improved battle simulation with line of sight, discrete weapon cooldowns, ammunition usage, range falloff, cover, morale, suppression, casualties, objective capture, and battle scoring.
- Animated unit graphics with facing arrows, status bars, movement bobbing, selection pulses, muzzle flashes, tracers, mortar shells, impacts, explosions, and smoke.
- Orders include Hold, Advance, Defend, Assault, Flank, and Retreat.
- Enemy neural commander makes a tactical decision every **2 simulated seconds**.
- Optional player-side AI mode lets the same persistent learning system command both factions.
- Every concluded battle automatically generates a new procedural map after **10 real seconds**.
- Neural weights and lifetime statistics are silently saved every **10 seconds**.
- Game state is silently autosaved every **5 seconds**.
- Autosave, chosen side, explored terrain, and neural brain are loaded automatically on startup.
- Atomic temporary-file replacement reduces save corruption risk.
- Standard library only; no third-party Python packages are required.

## Run on Windows

1. Install Python 3 from python.org and keep Tcl/Tk enabled during installation.
2. Double-click `run_game.bat`.

Or run from a terminal:

```powershell
py -3 main.py
```

## Controls

- **Left-click:** select a visible friendly unit.
- **Shift + left-click:** add or remove friendly units from the selection.
- **Right-click:** move selected friendly units to a destination.
- **Toolbar / Command tab:** set orders and stances.
- **New Battle:** generate a new map while preserving the selected side and neural brain.
- **New Save / Choose Side:** replace the current autosave and select Allied or Axis command.
- **Player AI Commander:** allow the neural brain to control the chosen player faction too.

## Persistent Data

On Windows, data is stored in:

```text
%APPDATA%\GatewayToCaen\
```

Files:

- `autosave.json` — battle state, player side, fog-of-war exploration, and post-battle countdown.
- `tactical_brain.json` — neural weights and lifetime learning statistics.
- `settings.json` — interface speed and preferred player side.

Starting a new battle or new save preserves the neural brain. Closing the application performs a final game, brain, and settings save.

## Neural Commander

The AI uses a `10 → 18 → 5` neural Q-network. Inputs represent unit strength, morale, ammunition, suppression, nearest enemy distance, objective distance, nearby force density, terrain cover, and map progress.

Its actions are Advance, Flank, Hold, Retreat, and Assault. Training rewards account for casualties inflicted and suffered, objective progress, cover use, retreat discipline, and battle results. The same brain continues learning forever unless manually reset in the Options tab.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```

The test suite covers neural persistence, procedural map generation, side-restricted orders, continuous movement, fog-of-war spotting, save restoration, and automatic ten-second map rotation.

## Project Layout

```text
main.py                         Application entry point
run_game.bat                    Windows launcher
gateway_to_caen/ui.py           Tkinter Windows 95 interface and graphics
gateway_to_caen/simulation.py   Tactical simulation, fog, combat, and battle state
gateway_to_caen/neural.py       Persistent neural Q-network
gateway_to_caen/persistence.py  Atomic JSON persistence
tests/                          Neural and simulation tests
```
