---
name: roblox-studio
description: Roblox Studio — Luau scripting, client/server, RemoteEvents, DataStores, Rojo projects, Open Cloud, importing 3D models.
domain: roblox
triggers: roblox, roblox studio, luau, rojo, remoteevent, datastore, leaderstats, tween, rbxl
---

# roblox-studio  (full docs: fetch_docs("roblox", "<key>"), keys via docs_index("roblox"))

## Where code runs
Script (server): ServerScriptService.  LocalScript (client): StarterPlayerScripts,
StarterCharacterScripts, StarterGui, ReplicatedFirst.  ModuleScript: require()'d, shared
code in ReplicatedStorage (both sides) or ServerStorage (server only).
Server owns truth. NEVER trust the client: validate every RemoteEvent argument, do
money/damage/inventory on the server, rate-limit.

## Basics
--!strict
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local part = Instance.new("Part")      -- set properties first, Parent LAST
part.Anchored = true
part.Size = Vector3.new(4, 1, 4)
part.Position = Vector3.new(0, 10, 0)
part.Color = Color3.fromRGB(255, 140, 60)
part.Material = Enum.Material.Neon
part.Parent = workspace

part.Touched:Connect(function(hit: BasePart)
    local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
    if hum then hum.Health -= 10 end
end)

Timing: task.wait(1), task.spawn(fn), task.delay(2, fn), task.defer(fn)
(never the deprecated wait()/spawn()/delay()). Per-frame: RunService.Heartbeat:Connect(function(dt) end)
Tween: TweenService:Create(part, TweenInfo.new(1, Enum.EasingStyle.Quad), {Position = Vector3.new(0, 20, 0)}):Play()
Types: local function add(a: number, b: number): number return a + b end
       type Item = { id: string, price: number }

## Players + leaderstats
Players.PlayerAdded:Connect(function(player)
    local stats = Instance.new("Folder"); stats.Name = "leaderstats"; stats.Parent = player
    local coins = Instance.new("IntValue"); coins.Name = "Coins"; coins.Parent = stats
    player.CharacterAdded:Connect(function(char) end)
end)

## Client -> server (RemoteEvent in ReplicatedStorage)
-- server
local buy = Instance.new("RemoteEvent"); buy.Name = "Buy"; buy.Parent = ReplicatedStorage
buy.OnServerEvent:Connect(function(player, itemId)
    if typeof(itemId) ~= "string" then return end   -- validate!
end)
-- client
ReplicatedStorage:WaitForChild("Buy"):FireServer("sword")
Server -> client: remote:FireClient(player, ...) / :FireAllClients(...). Request/response: RemoteFunction.

## DataStores (server only; publish the game + enable Studio API access in Game Settings > Security)
local store = game:GetService("DataStoreService"):GetDataStore("PlayerData_v1")
local ok, data = pcall(function() return store:GetAsync("u_" .. player.UserId) end)
pcall(function() store:UpdateAsync("u_" .. player.UserId, function(old) return newData end) end)
Save on Players.PlayerRemoving AND game:BindToClose. Always pcall; calls are rate-limited.

## ModuleScript
local M = {}
function M.greet(name: string): string return "hi " .. name end
return M

## Rojo (files on disk <-> Studio). default.project.json:
{ "name": "MyGame", "tree": { "$className": "DataModel",
  "ReplicatedStorage": { "Shared": { "$path": "src/shared" } },
  "ServerScriptService": { "Server": { "$path": "src/server" } },
  "StarterPlayer": { "StarterPlayerScripts": { "Client": { "$path": "src/client" } } } } }
File names: x.server.luau = Script, x.client.luau = LocalScript, x.luau = ModuleScript,
init.luau makes its folder that script. MAIN runs: rojo("build -o game.rbxlx") then
roblox_open("game.rbxlx"), or rojo("serve") + the Rojo Studio plugin for live sync.
Lint: luau_check("src").

## 3D models from Blender
Studio 3D Importer takes .fbx / .obj / .gltf / .glb. Keep each mesh under ~20k triangles,
apply transforms before export, check scale in the importer (Roblox units are studs).

## Open Cloud (optional, needs an API key from the Creator Dashboard)
Publish a place: POST https://apis.roblox.com/universes/v1/{universeId}/places/{placeId}/versions?versionType=Published
headers: x-api-key, Content-Type: application/octet-stream (.rbxl) or application/xml (.rbxlx); body = the file.
Check fetch_docs("roblox", "open-cloud") for Luau execution and other endpoints.
