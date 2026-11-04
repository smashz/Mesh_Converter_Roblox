-- Builds the vertical-slice Meadow region in Workspace.MBE_Meadow (Edit mode, run from the Studio
-- command bar or the MCP execute_luau tool). Safe to re-run: it replaces the previous build.
-- Layout (top-down, +Z is south): spawn at the south end, three enemy zones getting harder going
-- north, and Thornback Plateau (21 studs tall, Leaf Leap required) at the north end.

-- Y is the walkable ground height (terrain filled to y = 0 renders its surface at about y = 2).
local CENTER = Vector3.new(0, 2, 700)
local HALF = 160
local PLATEAU_CENTER = Vector3.new(0, 2, 585)
local PLATEAU_SIZE = 80
local PLATEAU_HEIGHT = 20

local rng = Random.new(20261104)

local old = workspace:FindFirstChild("MBE_Meadow")
if old then
	old:Destroy()
end

local meadow = Instance.new("Folder")
meadow.Name = "MBE_Meadow"

local function part(props: { [string]: any }, parent: Instance): Part
	local p = Instance.new("Part")
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	for k, v in props do
		(p :: any)[k] = v
	end
	p.Parent = parent
	return p
end

local function folder(name: string): Folder
	local f = Instance.new("Folder")
	f.Name = name
	f.Parent = meadow
	return f
end

-- Terrain ground ---------------------------------------------------------------------------------
local terrain = workspace.Terrain
-- The place already has a terrain floor (~y 8-10); carve the meadow area flat to y = 0 first.
terrain:FillBlock(CFrame.new(CENTER.X, 40, CENTER.Z), Vector3.new(HALF * 2 + 20, 80, HALF * 2 + 20), Enum.Material.Air)
task.wait()
terrain:FillBlock(CFrame.new(CENTER.X, -4, CENTER.Z), Vector3.new(HALF * 2 + 20, 8, HALF * 2 + 20), Enum.Material.Grass)
task.wait()
terrain:FillBlock(CFrame.new(CENTER.X + 84, -2, CENTER.Z + 96), Vector3.new(32, 4, 24), Enum.Material.Water)
-- Rolling hills on the edges so the boundary walls read as natural.
for i = 0, 15 do
	local angle = i / 16 * math.pi * 2
	local pos = CENTER + Vector3.new(math.cos(angle) * (HALF + 8), -6, math.sin(angle) * (HALF + 8))
	terrain:FillBall(pos, rng:NextNumber(22, 32), if i % 3 == 0 then Enum.Material.Rock else Enum.Material.Grass)
end
task.wait()

-- Boundary ---------------------------------------------------------------------------------------
local bounds = folder("Bounds")
for _, spec in {
	{ Vector3.new(0, 30, -HALF), Vector3.new(HALF * 2, 60, 2) },
	{ Vector3.new(0, 30, HALF), Vector3.new(HALF * 2, 60, 2) },
	{ Vector3.new(-HALF, 30, 0), Vector3.new(2, 60, HALF * 2) },
	{ Vector3.new(HALF, 30, 0), Vector3.new(2, 60, HALF * 2) },
} do
	part({ Name = "Wall", Position = CENTER + spec[1], Size = spec[2], Transparency = 1, CanQuery = false }, bounds)
end

-- Spawn ------------------------------------------------------------------------------------------
local spawn = Instance.new("SpawnLocation")
spawn.Name = "MeadowSpawn"
spawn.Anchored = true
spawn.Neutral = true
spawn.Duration = 5
spawn.Size = Vector3.new(14, 1, 14)
spawn.Position = CENTER + Vector3.new(0, 0.5, 130)
spawn.Material = Enum.Material.Grass
spawn.Color = Color3.fromRGB(120, 200, 110)
spawn.TopSurface = Enum.SurfaceType.Smooth
for _, d in spawn:GetChildren() do
	if d:IsA("Decal") then
		d:Destroy()
	end
end
spawn.Parent = meadow

-- Path from spawn to the plateau ----------------------------------------------------------------
part({
	Name = "Path",
	Position = CENTER + Vector3.new(0, 0.05, 15),
	Size = Vector3.new(10, 0.1, 230),
	Material = Enum.Material.Ground,
	Color = Color3.fromRGB(176, 144, 100),
	CanQuery = false,
}, meadow)

-- Thornback Plateau ------------------------------------------------------------------------------
local plateau = folder("ThornbackPlateau")
part({
	Name = "Cliff",
	Position = PLATEAU_CENTER + Vector3.new(0, PLATEAU_HEIGHT / 2, 0),
	Size = Vector3.new(PLATEAU_SIZE, PLATEAU_HEIGHT, PLATEAU_SIZE),
	Material = Enum.Material.Rock,
	Color = Color3.fromRGB(120, 110, 100),
}, plateau)
part({
	Name = "Top",
	Position = PLATEAU_CENTER + Vector3.new(0, PLATEAU_HEIGHT + 0.5, 0),
	Size = Vector3.new(PLATEAU_SIZE, 1, PLATEAU_SIZE),
	Material = Enum.Material.Grass,
	Color = Color3.fromRGB(90, 140, 70),
}, plateau)
-- Arena marker: the server publishes boss health on this part's attributes.
part({
	Name = "BossArena",
	Position = PLATEAU_CENTER + Vector3.new(0, PLATEAU_HEIGHT + 1.5, 0),
	Size = Vector3.new(4, 1, 4),
	Transparency = 1,
	CanCollide = false,
	CanQuery = false,
	CanTouch = false,
}, meadow)
-- Ring of stones on the plateau.
for i = 0, 9 do
	local angle = i / 10 * math.pi * 2
	part({
		Name = "ArenaStone",
		Size = Vector3.new(3, rng:NextNumber(4, 7), 3),
		CFrame = CFrame.new(PLATEAU_CENTER + Vector3.new(math.cos(angle) * 36, PLATEAU_HEIGHT + 3, math.sin(angle) * 36))
			* CFrame.Angles(0, angle, math.rad(rng:NextNumber(-8, 8))),
		Material = Enum.Material.Slate,
		Color = Color3.fromRGB(100, 100, 110),
	}, plateau)
end

-- Leap practice rock near the middle of the meadow (also needs Leaf Leap).
local practice = part({
	Name = "LeapRock",
	Position = CENTER + Vector3.new(-55, 7, 50),
	Size = Vector3.new(16, 14, 16),
	Material = Enum.Material.Rock,
	Color = Color3.fromRGB(130, 120, 110),
}, meadow)
part({
	Name = "LeapRockTop",
	Position = practice.Position + Vector3.new(0, 7.25, 0),
	Size = Vector3.new(16, 0.5, 16),
	Material = Enum.Material.Grass,
	Color = Color3.fromRGB(110, 170, 80),
}, meadow)

-- Signs ------------------------------------------------------------------------------------------
local signs = folder("Signs")
local function sign(position: Vector3, text: string)
	local post = part({
		Name = "Sign",
		Position = position + Vector3.new(0, 2.5, 0),
		Size = Vector3.new(0.6, 5, 0.6),
		Material = Enum.Material.Wood,
		Color = Color3.fromRGB(120, 85, 50),
	}, signs)
	local gui = Instance.new("BillboardGui")
	gui.Size = UDim2.fromOffset(260, 70)
	gui.StudsOffsetWorldSpace = Vector3.new(0, 4, 0)
	gui.MaxDistance = 90
	local l = Instance.new("TextLabel")
	l.Size = UDim2.fromScale(1, 1)
	l.BackgroundColor3 = Color3.fromRGB(70, 50, 30)
	l.BackgroundTransparency = 0.15
	l.TextColor3 = Color3.fromRGB(255, 240, 210)
	l.Font = Enum.Font.GothamBold
	l.TextScaled = true
	l.TextWrapped = true
	l.Text = text
	l.Parent = gui
	local c = Instance.new("UICorner")
	c.Parent = l
	gui.Parent = post
end
sign(CENTER + Vector3.new(12, 0, 122), "Welcome to the Meadow! Defeat wild creatures to grow and evolve.")
sign(CENTER + Vector3.new(12, 0, -48), "Thornback Plateau ahead. Evolve to learn Leaf Leap (jump twice) to climb it.")
sign(CENTER + Vector3.new(-42, 0, 50), "Leap Rock: practice your Leaf Leap here.")

-- Enemy spawns -----------------------------------------------------------------------------------
local spawns = folder("EnemySpawns")
local function enemySpawn(enemyType: string, offset: Vector3)
	local p = part({
		Name = enemyType .. "Spawn",
		Position = CENTER + offset,
		Size = Vector3.new(2, 0.2, 2),
		Transparency = 1,
		CanCollide = false,
		CanQuery = false,
		CanTouch = false,
	}, spawns)
	p:SetAttribute("EnemyType", enemyType)
end
for _, o in { Vector3.new(-30, 0.5, 80), Vector3.new(25, 0.5, 75), Vector3.new(-10, 0.5, 60), Vector3.new(40, 0.5, 50) } do
	enemySpawn("Mossling", o)
end
for _, o in { Vector3.new(-60, 0.5, 15), Vector3.new(0, 0.5, 5), Vector3.new(55, 0.5, 10), Vector3.new(-25, 0.5, -10) } do
	enemySpawn("Buzzleaf", o)
end
for _, o in { Vector3.new(-45, 0.5, -50), Vector3.new(40, 0.5, -55), Vector3.new(0, 0.5, -45) } do
	enemySpawn("Rockmole", o)
end
enemySpawn("Thornback", PLATEAU_CENTER - CENTER + Vector3.new(0, PLATEAU_HEIGHT + 1, 0))

meadow.Parent = workspace
task.wait()

-- Decoration (trees, rocks, flowers), kept away from the path, plateau, spawn and enemy zones -----
local decor = folder("Decor")
local avoid = { { CENTER + Vector3.new(0, 0, 130), 22 }, { CENTER + Vector3.new(-55, 0, 50), 16 } }
for _, s in spawns:GetChildren() do
	table.insert(avoid, { (s :: BasePart).Position, 9 })
end
local function blocked(pos: Vector3): boolean
	if math.abs(pos.X - CENTER.X) < 12 then
		return true
	end
	if math.abs(pos.X - PLATEAU_CENTER.X) < PLATEAU_SIZE / 2 + 32 and math.abs(pos.Z - PLATEAU_CENTER.Z) < PLATEAU_SIZE / 2 + 32 then
		return true
	end
	for _, a in avoid do
		if (Vector3.new(pos.X, 0, pos.Z) - Vector3.new(a[1].X, 0, a[1].Z)).Magnitude < a[2] then
			return true
		end
	end
	return false
end
local function randomSpot(margin: number): Vector3?
	for _ = 1, 30 do
		local pos = CENTER + Vector3.new(rng:NextNumber(-HALF + margin, HALF - margin), 0, rng:NextNumber(-HALF + margin, HALF - margin))
		if not blocked(pos) then
			return pos
		end
	end
	return nil
end

local leafColors = { Color3.fromRGB(70, 150, 70), Color3.fromRGB(90, 170, 80), Color3.fromRGB(60, 130, 80) }
for _ = 1, 50 do
	local pos = randomSpot(8)
	if pos then
		local h = rng:NextNumber(8, 13)
		local tree = Instance.new("Model")
		tree.Name = "Tree"
		local trunk = part({
			Name = "Trunk",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(h, 2, 2),
			CFrame = CFrame.new(pos + Vector3.new(0, h / 2, 0)) * CFrame.Angles(0, 0, math.rad(90)),
			Material = Enum.Material.Wood,
			Color = Color3.fromRGB(110, 80, 50),
		}, tree)
		for i = 1, 3 do
			local size = rng:NextNumber(6, 9)
			part({
				Name = "Leaves",
				Shape = Enum.PartType.Ball,
				Size = Vector3.one * size,
				Position = pos + Vector3.new(rng:NextNumber(-2.5, 2.5), h + rng:NextNumber(-1, 2.5), rng:NextNumber(-2.5, 2.5)),
				Material = Enum.Material.Grass,
				Color = leafColors[i],
			}, tree)
		end
		tree.PrimaryPart = trunk
		tree.Parent = decor
	end
end
task.wait()
for _ = 1, 18 do
	local pos = randomSpot(6)
	if pos then
		local s = rng:NextNumber(2, 5)
		part({
			Name = "Rock",
			Size = Vector3.new(s * rng:NextNumber(1, 1.6), s, s),
			CFrame = CFrame.new(pos + Vector3.new(0, s / 3, 0)) * CFrame.Angles(rng:NextNumber(-0.3, 0.3), rng:NextNumber(0, 6.28), rng:NextNumber(-0.3, 0.3)),
			Material = Enum.Material.Rock,
			Color = Color3.fromRGB(125, 120, 115),
		}, decor)
	end
end
local flowerColors = { Color3.fromRGB(255, 120, 160), Color3.fromRGB(255, 230, 90), Color3.fromRGB(170, 140, 255), Color3.fromRGB(255, 255, 255) }
for _ = 1, 80 do
	local pos = randomSpot(4)
	if pos then
		part({
			Name = "Flower",
			Shape = Enum.PartType.Ball,
			Size = Vector3.one * 0.8,
			Position = pos + Vector3.new(0, 0.5, 0),
			Color = flowerColors[rng:NextInteger(1, #flowerColors)],
			CanCollide = false,
			CanQuery = false,
			CanTouch = false,
		}, decor)
	end
end

return "Meadow built: " .. #meadow:GetDescendants() .. " instances"
