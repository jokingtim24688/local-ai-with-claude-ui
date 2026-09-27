---
name: roblox-obby-builder
description: Roblox obby builder — generate a full obby place from a plan, then add Luau mechanics.
domain: roblox
triggers: roblox, obby, obstacle course, parkour, roblox studio, rbxl, rbxlx, luau, checkpoint, kill brick, lava, stages, tower of hell
---
# Roblox Obby Builder skill

STEP 1 — the course is generated from a plan (you do NOT place parts by hand):
```plan file=plans/<name>.json run
{"kind":"obby","name":"NeonObby","stages":12,"difficulty":"medium","theme":"neon","seed":3}
```
difficulty: easy | medium | hard. theme: neon | classic | lava | candy. stages 3-60.
That builds roblox/<Name>/<Name>.rbxlx with workspace.Obby holding parts named
Start (SpawnLocation), Platform<stage>_<n> (n = 0,1,2), KillBrick, Checkpoint<stage>, Finish,
and a rules script (kill bricks, checkpoints + respawn, Wins leaderstat). Then roblox_open it.

STEP 2 (optional) — extra mechanics as ONE server script:
```luau file=roblox/<Name>/src/server/<Feature>.server.luau run
```
(`run` = luau_check.)

LUAU RULES
- Server Script for anything that changes the world or scores. Never trust the client.
- `task.wait` `task.spawn` `task.delay` — never `wait()` `spawn()` `delay()`.
- `game:GetService("X")` for services. Find course parts with
  `workspace:WaitForChild("Obby")` then `:GetChildren()` and `string.match(part.Name, "^Platform%d+_1$")`.
- Set properties first, Parent last. Use `local`. `~=` is not-equal, `..` joins strings.

TEMPLATE — moving + vanishing platforms
```luau file=roblox/NeonObby/src/server/Mechanics.server.luau run
local TweenService = game:GetService("TweenService")
local course = workspace:WaitForChild("Obby")

for _, part in course:GetChildren() do
	if not part:IsA("BasePart") then continue end
	if string.match(part.Name, "^Platform%d+_1$") then
		-- slides 8 studs side to side forever
		local info = TweenInfo.new(2, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut, -1, true)
		TweenService:Create(part, info, {CFrame = part.CFrame + Vector3.new(8, 0, 0)}):Play()
	elseif string.match(part.Name, "^Platform%d+_2$") then
		-- fades out and back every few seconds
		task.spawn(function()
			while true do
				task.wait(2)
				part.Transparency = 0.8
				part.CanCollide = false
				task.wait(1.5)
				part.Transparency = 0
				part.CanCollide = true
			end
		end)
	end
end
```
