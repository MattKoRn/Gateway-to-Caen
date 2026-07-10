# Gateway to Caen: Tactical Command

A dependency-free **Python/Tkinter tactical campaign** with procedural maps, persistent formations and resources, side-aware fog of war, runtime-generated and cached unit artwork and sound effects, a smart conventional enemy commander, and a neural virtual player that acts through a visible mouse cursor.

> This is an original clean-room project inspired by the broad tactical-command genre. It contains no proprietary Close Combat code, artwork, maps, audio, scenarios, or data and is not affiliated with the original publishers or developers.

## Version 0.6.3 highlights

### Responsiveness and tactical-map-only neural control

- The battlefield renderer sleeps while another main tab is open and adapts its frame interval to actual render cost.
- Hidden trees, intelligence panels, neural statistics, and requisition rosters are no longer rebuilt every 250 milliseconds.
- Human clicks and keypresses always pause and hide the neural pointer for twelve seconds; stale invisible modal grabs are released automatically.
- The neural pointer is restricted to the Battlefield tab and pauses whenever any other tab is open.
- It cannot activate tabs, subtabs, buttons, checkboxes, trees, text panels, comboboxes, settings, save controls, or other non-map widgets.
- The auto-camera follows the neural pointer only while it is operating on the tactical map.

### Persistent campaign

- Every living formation retains its identity, personnel, ammunition, morale, experience, kills, and battle count across maps and sessions.
- Allied and Axis manpower, supplies, and command points persist separately.
- Destroyed formations remain lost; survivors redeploy on the next generated battlefield.
- Campaign data is stored alongside the normal battle autosave and neural-brain file.
- Automatic battle replacement still occurs ten seconds after a result.

### Neural requisition

Before each map, the persistent neural network evaluates both faction rosters and resources, requisitions affordable formations, and immediately deducts their manpower, supply, and command-point costs. Its purchases and rationale appear in the new **Requisition** tab.

Formation classes are Rifle, Support, Scout, Mortar, and Armour. The tab includes:

- both faction resource pools;
- the complete persistent rosters;
- unit costs;
- recent neural purchases and rationale;
- current adaptive difficulty and reward multipliers;
- an optional button to queue additional neural purchases for the next map.

### Visible neural mouse commander

The player faction receives **no direct simulation auto-orders**. When enabled, the neural network instead behaves like a visible virtual player:

1. It moves a custom neural cursor toward a friendly formation.
2. It visibly left-clicks the unit.
3. It chooses and clicks Hold, Advance, Flank, Retreat, or Assault.
4. It moves to a battlefield destination.
5. It right-clicks through the same tactical-map handler used by a human.
6. It pauses to observe the result and trains from casualties, survival, score, and objective progress.

The cursor uses an expanded `18 → 32 → 5` Q-network with adaptive exploration, prioritised replay memory, gradient clipping, learning-rate decay, and legacy-brain migration. The auto-camera follows the cursor and dynamically zooms around its current action. Manual input pauses and hides the virtual player for twelve seconds.

The neural pointer is strictly restricted to the tactical map. It cannot open tabs or subtabs, press interface buttons, change settings, browse lists, or operate any other non-map control.

### Smart conventional enemy AI

The opposing faction deliberately does **not** use the neural network. It uses a coordinated utility commander that:

- assigns role-specific behaviour to infantry, support teams, scouts, mortars, and armour;
- concentrates on valuable and contested objectives;
- identifies weak visible contacts;
- protects indirect-fire teams;
- coordinates support weapons behind advancing infantry;
- performs flanking reconnaissance and armoured breakthroughs;
- retreats suppressed, depleted, or low-morale formations;
- adjusts force quality and aggression to campaign difficulty.

### Adaptive difficulty and rewards

Recent player wins and losses move enemy difficulty between `0.65×` and `1.80×`. Enemy experience, morale, purchasing pressure, and tactical aggression respond to that value. Persistent campaign rewards move with the same performance curve, so stronger opposition produces greater returns while a losing streak softens both challenge and rewards.

### Improved procedural maps

Each map selects a different operational theme, such as:

- Bocage Labyrinth
- Village Crossroads
- Wooded Ridge
- Muddy Causeway
- Open Farmland
- Twin-Road Salient

Terrain is generated as coherent road networks, field boundaries, village clusters, wooded ridges, muddy corridors, hedgerow lanes, deployment zones, obstacles, and capturable locations rather than unrelated random blobs. Every map rolls four unique mission objectives from capture, defence, reconnaissance, breakthrough, force-preservation, and anti-armour goals.

### Graphics and sound

- Runtime-generated PNG artwork for every Allied and Axis formation class at three zoom levels.
- A custom neural cursor image and mission icons.
- Richer painted terrain, roads, forests, villages, mud, hedgerows, shadows, obstacles, selection reticles, direction indicators, status bars, destination markers, smoke, tracers, and explosions.
- Runtime-generated WAV assets for UI clicks, selections, orders, requisitions, objectives, battle starts, gunfire, explosions, victory, defeat, and errors.
- Windows uses asynchronous `winsound`; other platforms fall back safely to the Tk bell.
- Audio can be disabled in **Options → Audio & Visual**.

### Performance

- Cached terrain and fog layers continue to transform with the camera instead of being rebuilt each frame.
- Spatial hashes accelerate nearby-unit, collision, target, and obstacle searches as persistent rosters grow.
- Unit sprites are loaded lazily and cached by side, class, and zoom tier.
- Combat effects and sounds are throttled and capped.
- Off-screen formation artwork is skipped.

## Existing systems

- Windows-inspired menus, toolbar, raised panels, status bar, tabs, and subtabs.
- Allied or Axis player-side selection with mirrored Axis presentation.
- Persistent fog of war and explored terrain.
- Smooth movement, obstacle steering, collision, formation separation, and blocked destination correction.
- Physical walls, bunkers, roadblocks, anti-tank obstacles, craters, rubble, trees, and smoking wrecks.
- Weapon cooldowns, line of sight, cover, armour, suppression, morale, casualties, objectives, weather, and animated combat effects.
- Full War Diary for battle and campaign events.
- Silent battle autosaves every five seconds and neural-brain saves every ten seconds.
- Manually dismissible offline report with days, hours, minutes, seconds, and rewards.
- Atomic JSON persistence.
- Standard-library runtime only.

## Controls

| Control | Action |
|---|---|
| `N` | Toggle neural mouse commander |
| `C` | Toggle auto-camera |
| `F` | Focus selected formation |
| Mouse wheel | Manual zoom |
| Middle-button drag | Manual camera pan |
| Left-click | Manual friendly selection |
| Shift + left-click | Manual multi-selection |
| Right-click | Manual movement destination |
| Toolbar / Command tab | Manual order selection |

Manual interaction temporarily yields control from the neural cursor.

## Run on Windows

1. Install Python 3 with Tcl/Tk enabled.
2. Double-click `run_game.bat`.

Or run:

```bash
python main.py
```

No third-party runtime packages are required.

## Save locations

On Windows, files are stored under `%APPDATA%\GatewayToCaen`:

- `autosave.json` — current battlefield
- `campaign_state.json` — persistent rosters, resources, difficulty, objectives, and requisitions
- `tactical_brain.json` — neural cursor and requisition learning
- `campaign_profile.json` — offline progress rewards
- `settings.json` — speed, side, audio, camera, and neural-cursor preferences
