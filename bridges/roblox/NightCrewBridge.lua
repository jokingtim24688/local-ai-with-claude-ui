--[[ Night Crew Bridge — Roblox Studio plugin.
Lets the local Night Crew agents edit the open place. It only talks to
http://127.0.0.1:9877 (the Night Crew app on this PC). Every change is one undo step.
Toolbar: Night Crew > Connect (toggles). Studio asks once to allow HTTP to 127.0.0.1. ]]

local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local LogService = game:GetService("LogService")
local RunService = game:GetService("RunService")
local Selection = game:GetService("Selection")

if RunService:IsRunning() then return end -- not inside playtest copies

local BASE = "http://127.0.0.1:9877"
local toolbar = plugin:CreateToolbar("Night Crew")
local button = toolbar:CreateButton("Connect", "Let Night Crew agents edit this place", "rbxasset://textures/StudioToolbox/AssetPreview/Settings.png")
button.ClickableWhenViewportHidden = true

local enabled = plugin:GetSetting("nc_enabled") ~= false
local logs = {}
LogService.MessageOut:Connect(function(msg, kind)
	table.insert(logs, kind.Name .. ": " .. msg)
	if #logs > 300 then table.remove(logs, 1) end
end)

-- ---------- helpers ----------
local function resolve(path)
	if typeof(path) ~= "string" or path == "" or path == "game" then return game end
	path = path:gsub("^game%.", "")
	local node = game
	for seg in string.gmatch(path, "[^%.]+") do
		local nxt = node:FindFirstChild(seg)
		if not nxt and node == game then
			local ok, svc = pcall(game.GetService, game, seg)
			if ok then nxt = svc end
		end
		if not nxt then error("not found: " .. path .. " (missing '" .. seg .. "')") end
		node = nxt
	end
	return node
end

local function num3(v)
	if typeof(v) == "table" then return v[1] or 0, v[2] or 0, v[3] or 0 end
	if typeof(v) == "number" then return v, v, v end
	local t = {}
	for n in string.gmatch(tostring(v), "[-%d%.eE]+") do table.insert(t, tonumber(n)) end
	return t[1] or 0, t[2] or 0, t[3] or 0
end

local function toColor(v)
	if typeof(v) == "string" and v:sub(1, 1) == "#" then return Color3.fromHex(v) end
	if typeof(v) == "string" then
		local ok, bc = pcall(BrickColor.new, v)
		if ok then return bc.Color end
	end
	local r, g, b = num3(v)
	if r > 1 or g > 1 or b > 1 then return Color3.fromRGB(r, g, b) end
	return Color3.new(r, g, b)
end

-- convert a JSON value to whatever type the property already has
local function coerce(inst, prop, v)
	local cur = inst[prop]
	local t = typeof(cur)
	if t == "Vector3" then return Vector3.new(num3(v))
	elseif t == "Color3" then return toColor(v)
	elseif t == "BrickColor" then return BrickColor.new(toColor(v))
	elseif t == "CFrame" then
		if typeof(v) == "table" and #v >= 6 then
			return CFrame.new(v[1], v[2], v[3]) * CFrame.Angles(math.rad(v[4]), math.rad(v[5]), math.rad(v[6]))
		end
		return CFrame.new(num3(v)) * (cur - cur.Position)
	elseif t == "EnumItem" then return cur.EnumType[tostring(v)]
	elseif t == "UDim2" then return UDim2.new(v[1] or 0, v[2] or 0, v[3] or 0, v[4] or 0)
	elseif t == "Vector2" then return Vector2.new(v[1] or 0, v[2] or 0)
	elseif t == "Instance" or (cur == nil and typeof(v) == "string" and prop == "Parent") then return resolve(v)
	elseif t == "number" then return tonumber(v)
	elseif t == "boolean" then return v == true or v == "true"
	elseif t == "string" then return tostring(v)
	end
	return v
end

local function apply(inst, props)
	for k, v in pairs(props or {}) do
		if k ~= "Parent" then
			local ok, err = pcall(function() inst[k] = coerce(inst, k, v) end)
			if not ok then error("can't set " .. k .. ": " .. tostring(err)) end
		end
	end
end

local function short(inst)
	local d = { name = inst.Name, class = inst.ClassName }
	if inst:IsA("BasePart") then
		local p, s = inst.Position, inst.Size
		d.pos = { math.floor(p.X * 10) / 10, math.floor(p.Y * 10) / 10, math.floor(p.Z * 10) / 10 }
		d.size = { math.floor(s.X * 10) / 10, math.floor(s.Y * 10) / 10, math.floor(s.Z * 10) / 10 }
	end
	return d
end

local function tree(inst, depth)
	local d = short(inst)
	local kids = inst:GetChildren()
	if depth > 0 and #kids > 0 then
		d.children = {}
		for i, c in ipairs(kids) do
			if i > 60 then d.more = #kids - 60 break end
			table.insert(d.children, tree(c, depth - 1))
		end
	elseif #kids > 0 then
		d.kids = #kids
	end
	return d
end

local function recorded(label, fn)
	local rec
	local ok0, id = pcall(function() return ChangeHistoryService:TryBeginRecording(label) end)
	if ok0 then rec = id end
	local ok, res = pcall(fn)
	if rec then pcall(function() ChangeHistoryService:FinishRecording(rec, Enum.FinishRecordingOperation.Commit) end)
	else pcall(function() ChangeHistoryService:SetWaypoint(label) end) end
	if not ok then error(res, 0) end
	return res
end

-- ---------- operations ----------
local ops = {}

function ops.ping() return { place = game.Name, placeId = game.PlaceId } end

function ops.tree(a) return tree(resolve(a.path or "Workspace"), math.clamp(tonumber(a.depth) or 2, 0, 5)) end

function ops.get(a)
	local inst = resolve(a.path)
	local out = short(inst)
	for _, p in ipairs(a.props or {}) do
		local ok, v = pcall(function() return inst[p] end)
		out[p] = ok and tostring(v) or ("<" .. tostring(v) .. ">")
	end
	return out
end

function ops.create(a)
	return recorded("Night Crew: create", function()
		local inst = Instance.new(a.class or "Part")
		if a.name and a.name ~= "" then inst.Name = a.name end
		if inst:IsA("BasePart") then inst.Anchored = true end
		apply(inst, a.props)
		inst.Parent = resolve(a.parent or "Workspace")
		return inst:GetFullName()
	end)
end

function ops.set(a)
	return recorded("Night Crew: set", function()
		local inst = resolve(a.path)
		apply(inst, a.props)
		if a.props and a.props.Parent then inst.Parent = resolve(a.props.Parent) end
		return inst:GetFullName()
	end)
end

function ops.delete(a)
	return recorded("Night Crew: delete", function()
		local names = {}
		for _, p in ipairs(typeof(a.paths) == "table" and a.paths or { a.paths or a.path }) do
			local inst = resolve(p)
			if inst == game or inst.Parent == game then error("refusing to delete " .. p) end
			table.insert(names, inst:GetFullName())
			inst:Destroy()
		end
		return names
	end)
end

function ops.script(a)
	return recorded("Night Crew: script", function()
		local parent = resolve(a.parent or "ServerScriptService")
		local kind = a.kind or "Script"
		local s = parent:FindFirstChild(a.name or "NightCrewScript")
		if s and s.ClassName ~= kind then s:Destroy() s = nil end
		if not s then
			s = Instance.new(kind)
			s.Name = a.name or "NightCrewScript"
			s.Parent = parent
		end
		s.Source = a.source or ""
		return s:GetFullName()
	end)
end

function ops.run(a)
	if not loadstring then error("loadstring is not available to plugins here; use create/set/script") end
	local fn, err = loadstring(a.code or "")
	if not fn then error("syntax: " .. tostring(err), 0) end
	local out = {}
	local function grab(...)
		local t = {}
		for i = 1, select("#", ...) do t[i] = tostring((select(i, ...))) end
		table.insert(out, table.concat(t, " "))
	end
	local env = setmetatable({ print = grab, warn = function(...) grab("WARN:", ...) end }, { __index = getfenv() })
	setfenv(fn, env)
	local res = recorded("Night Crew: run", function() return table.pack(fn()) end)
	for i = 1, res.n do table.insert(out, "=> " .. tostring(res[i])) end
	return table.concat(out, "\n")
end

function ops.logs(a)
	local n = tonumber(a.count) or 40
	local t = {}
	for i = math.max(1, #logs - n + 1), #logs do table.insert(t, logs[i]) end
	if a.clear then logs = {} end
	return table.concat(t, "\n")
end

function ops.selection()
	local t = {}
	for _, s in ipairs(Selection:Get()) do table.insert(t, s:GetFullName()) end
	return t
end

-- ---------- poll loop ----------
local running = false
local function loop()
	if running then return end
	running = true
	while enabled do
		local ok, res = pcall(function()
			return HttpService:RequestAsync({ Url = BASE .. "/poll", Method = "GET", Headers = { ["X-NC"] = "1" } })
		end)
		if ok and res.StatusCode == 200 and res.Body ~= "" then
			local cmd = HttpService:JSONDecode(res.Body)
			local f = ops[cmd.op]
			local ok2, out = pcall(function()
				if not f then error("unknown op " .. tostring(cmd.op), 0) end
				return f(cmd.args or {})
			end)
			pcall(function()
				HttpService:RequestAsync({ Url = BASE .. "/result", Method = "POST",
					Headers = { ["X-NC"] = "1", ["Content-Type"] = "application/json" },
					Body = HttpService:JSONEncode({ id = cmd.id, ok = ok2, output = ok2 and out or tostring(out) }) })
			end)
		elseif not ok or res.StatusCode ~= 204 then
			task.wait(3) -- app not running yet
		end
	end
	running = false
end

local function paint()
	button:SetActive(enabled)
end

button.Click:Connect(function()
	enabled = not enabled
	plugin:SetSetting("nc_enabled", enabled)
	paint()
	if enabled then task.spawn(loop) end
end)

paint()
if enabled then task.spawn(loop) end
