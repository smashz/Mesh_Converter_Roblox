# Monster Battle Evolution: vertical slice

A playable prototype for the Roblox Studio place **Monster Battle Evolution** (placeId 120729653051177).
The player starts as a small creature, fights wild creatures in a meadow, earns XP and evolution
energy, evolves down one of two branches, unlocks a traversal ability and takes on a boss.
All names, stats and placeholder models are original. See `PLANNING.md` for the design, the
architecture and the known limitations.

## What's in the place right now

Everything below is already in the Studio place (pushed and built over Studio MCP on 2026-11-04):

| Where in Studio | What |
|---|---|
| `ReplicatedStorage.MBE` | Config (creatures, enemies, progression), `Remotes`, `ImportedMesh` (runtime mesh builder) |
| `ServerScriptService.MBE` | `Main` (server entry), `PlayerService`, `EnemyService`, `CombatService`, `CreatureVisuals` |
| `StarterPlayer.StarterPlayerScripts.MBE` | `Client` (input + Leaf Leap), `HUD`, `Effects`, `ImportedMeshes` |
| `Workspace.MBE_Meadow` | The Meadow map, built by `tools/build_meadow.lua`, centered at (0, 2, 700) |
| `ServerStorage.MBE_Models` | Creature model templates: your own, or converted playtest stand-ins (see below) |
| `ReplicatedStorage.MBE_PlaytestAssets` | Mesh/texture data for the converted stand-ins |

The source of truth is `src/` in this folder. Studio's copies are generated from it.

## How to test in Studio

1. Open **Monster Battle Evolution** and press **Play** (F5). You spawn in the Meadow as **Pipkit**.
2. Controls:
   - **Click / F**: attack, aimed at the mouse
   - **Q**: special (after evolving)
   - **Space twice**: Leaf Leap (after evolving)
   - **E**: open or close the evolve panel
   - Gamepad: X attacks, Y uses the special. Touch: ATK and SP buttons.
3. Defeat Mosslings, Buzzleafs and Rockmoles to reach **level 5 and 100 energy**. The evolve panel
   then offers **Bramblehorn** (power) or **Galewing** (speed).
4. Use Leaf Leap on the Leap Rock, then jump up the cliff of **Thornback Plateau** (north end) to fight
   **Old Thornback**. Dodge its slam by leaving the area when the boss glows orange.

### Skipping the grind (Studio only)

The server creates `ServerStorage.MBE_Dev` only inside Studio. While a playtest is running, paste this into
the command bar with the **Server** context selected:

```lua
game.ServerStorage.MBE_Dev:Invoke("grant", game.Players:GetPlayers()[1], 280, 100) -- XP, energy
```

## Re-syncing after editing `src/`

Rojo isn't installed, so `tools/push.js` syncs over Studio MCP instead. It replaces only the three
`MBE` folders listed in `default.project.json`. Studio must be open, with the playtest stopped.

```bash
cd tools
node push.js                                   # push all scripts from src/
node mcp_call.js luau build_meadow.lua Edit    # rebuild Workspace.MBE_Meadow (safe to re-run)
```

If you install Rojo later, `default.project.json` already uses its standard layout.

## Using your own creature models

The primitive-part creatures are placeholders. To swap one out, put a **Model** into
`ServerStorage.MBE_Models` and name it after the form or enemy id: `Pipkit`, `Bramblehorn`, `Galewing`,
`Mossling`, `Buzzleaf`, `Rockmole` or `Thornback`. The game then:

- uses that model instead of the placeholder,
- scales it to the placeholder's height,
- stands it on the ground and welds it to the creature.

Two optional attributes on the Model adjust it:

- `Height` (number): the height to scale to, in studs.
- `YawOffset` (degrees): turns a model that faces the wrong way.

Scripts and Humanoids inside the model are removed. Use only models you have the rights to in anything
you publish.

## Playtest stand-ins converted from `poke_assets` (private playtests only)

`poke_assets` holds mined Pokémon GO files, property of The Pokémon Company and Niantic. The converter
below turns some of them into stand-in creature models **for private Studio playtests only**. Nothing is
uploaded to Roblox: the mesh and texture data sit inside the place as ModuleScripts and are built at
runtime with `EditableMesh` / `EditableImage`. **Before publishing or sharing the place, run
`node tools/push_assets.js --remove`** and save.

Current stand-ins (`tools/converter/assets.json`):

| Game id | Source |
|---|---|
| Pipkit | pm0001 |
| Bramblehorn | pm0002 |
| Galewing | pm0017 |
| Thornback (boss) | pm0003 |
| Mossling | pm0043 |
| Buzzleaf | pm0015 |
| Rockmole | pm0050 |

### One-time Studio setting (required)

Roblox blocks runtime meshes until the place allows them: in Studio open **File → Experience Settings →
Security**, turn on **Allow Mesh / Image APIs**, and press **Save**. Until then the game logs
`[MBE] imported models disabled, using placeholders` and keeps the primitive placeholders.

### Converting and pushing

Needs Blender 5.x (default path `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`, or set
`BLENDER`) and Node.js. Studio must be open on the place, with the playtest stopped.

```bash
node tools/converter/convert.js            # all ids in assets.json -> build/playtest_assets/<Id>.json
node tools/converter/convert.js Pipkit     # just one
node tools/push.js                         # scripts (only needed after editing src/)
node tools/push_assets.js                  # data + templates into Studio (or: push_assets.js Pipkit)
node tools/push_assets.js --remove         # take every converted model back out
```

The converter also fixes the Pokémon GO eye overlay used by these files. It composites the separate
Eye/Face layer (or the second-UV eye tile) over the body before packing the texture atlas, so Roblox
does not render the eye layer as a transparent blue blob. Rebuilding all seven ids is reproducible
with the first command above. The local visual checks are in `screens/eyes_Pipkit_after.png`,
`screens/eyes_Mossling_after.png` and `screens/eyes_all_models.png`; Studio Playtest still requires
**Allow Mesh / Image APIs** to be enabled first.

To use another model, add a line to `assets.json` (`source` is any `.fbx`, `.obj`, `.glb` or `.gltf`;
optional `height`, `yaw`, `tex`, `pose`), then convert and push. `push_assets.js` never replaces a
hand-made model you put in `MBE_Models` yourself.
