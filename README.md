# Gateway to Caen: Tactical Command

A dependency-free **Tkinter tactical RTS prototype** with a Windows 95 command interface, procedural battlefields, persistent neural commanders, side-aware fog of war, offline campaign progress, and a smooth action-following tactical camera.

> This is an original clean-room project inspired by the broad tactical-command genre. It does not contain proprietary Close Combat code, artwork, maps, audio, scenarios, or data, and it is not affiliated with the original game's publishers or developers.

## Features

- Windows 95-inspired menus, toolbar, raised panels, status bar, main tabs, and sub-tabs.
- New saves ask whether the player commands **Allied** or **Axis** forces.
- Axis command mirrors the battlefield so the player's formations remain on the left.
- Side-aware fog of war with persistent explored terrain and concealed enemy contacts.
- Procedural 26×17 battlefields containing roads, fields, woods, hedgerows, villages, mud, and capturable objectives.
- Rifle, support, scout, mortar, and armour formations with morale, ammunition, suppression, casualties, experience, and orders.
- Smooth accelerated troop movement, turning, formation separation, and roughly 30 FPS animation.
- Line of sight, weapon cooldowns, range falloff, terrain cover, objective capture, animated projectiles, explosions, smoke, and weather.
- A persistent `10 → 18 → 5` neural Q-network that decides every two simulated seconds and learns across maps and sessions.
- Silent game autosaves every **5 seconds** and neural-brain saves every **10 seconds**.
- Automatic procedural map replacement **10 seconds** after a battle concludes.
- Offline progress with a manually dismissible command report showing days, hours, minutes, seconds, and persistent campaign rewards.
- Atomic JSON writes to reduce save corruption risk.
- Standard library only; no third-party Python packages are required.

## Auto Camera

The tactical map includes a toggleable action camera that:

- prioritises selected units;
- follows recent hits, weapon fire, shell impacts, advancing formations, and contested objectives;
- smoothly scrolls between action areas instead of snapping;
- dynamically zooms in for individual units and firefights;
- zooms out to frame groups, objectives, and after-action overviews;
- displays its current target and zoom level in a battlefield HUD;
- remembers whether auto camera was enabled between sessions.

Manual camera controls remain available:

- **Mouse wheel:** zoom in or out and switch to manual camera.
- **Middle-button drag:** pan and switch to manual camera.
- **C:** toggle auto camera.
- **F:** focus the selected unit or formation and enable auto camera.
- **Double-click:** focus selected units.
- **Focus / − / + / Overview:** toolbar camera controls.

## Other Controls

- **Left-click:** select a visible friendly unit.
- **Shift + left-click:** add or remove units from the selection.
- **Right-click:** issue a movement destination.
- **Toolbar / Command tab:** set Hold, Advance, Defend, Assault, Flank, or Retreat.
- **New Battle:** generate a new map while preserving side, brain, campaign profile, and camera preference.
- **New Save / Choose Side:** replace the current battlefield save and choose Allied or Axis command.
- **Player AI Commander:** let the persistent neural brain command the player's faction too.

## Run on Windows

1. Install Python 3 and keep Tcl/Tk enabled during installation.
2. Double-click `run_game.bat`.

Or run:

```powershell
py -3 main.py
```

## Persistent Data

On Windows, files are stored in:

```text
%APPDATA%\GatewayToCaen\
```

- `autosave.json` — battle state, chosen side, fog exploration, and post-battle countdown.
- `tactical_brain.json` — neural weights and lifetime learning statistics.
- `settings.json` — simulation speed, preferred side, and auto-camera toggle.
- `campaign_profile.json` — last active timestamp, offline rewards, campaign reserves, sessions, and pending report.

Starting a new battle or save preserves the neural brain and campaign reserves. Closing performs a final game, brain, profile, and settings save.

## Offline Rewards

Reward rates are deterministic and capped at 30 rewarded days per claim:

- 1 Command Point per minute.
- 1 Supply per 10 seconds.
- 1 Reinforcement Token per 30 minutes.
- 1 Intelligence Report per hour.

The report remains pending until manually dismissed and reappears after a crash without granting the same offline interval twice.

## Tests

```powershell
py -3 -m unittest discover -s tests -v
```

The suite covers neural persistence, procedural battles, side-restricted orders, continuous movement, fog spotting, save restoration, automatic map rotation, offline rewards and report persistence, camera target priority, dynamic zoom, map-edge clamping, and after-action overview behaviour.

## Project Layout

```text
main.py                            Application entry point
run_game.bat                       Windows launcher
gateway_to_caen/ui.py              Base Windows 95 Tkinter interface
gateway_to_caen/enhanced_ui.py     Offline progress, campaign UI, and v0.4 shell
gateway_to_caen/camera.py          Auto-camera target selection and viewport transforms
gateway_to_caen/terrain_graphics.py Cached terrain, fog, and objectives
gateway_to_caen/unit_graphics.py   Units, combat effects, and weather
gateway_to_caen/simulation.py      Tactical simulation and battle state
gateway_to_caen/neural.py          Persistent neural Q-network
gateway_to_caen/offline.py         Offline rewards and campaign profile
gateway_to_caen/persistence.py     Atomic JSON persistence
tests/                             Neural, simulation, offline, and camera tests
```
