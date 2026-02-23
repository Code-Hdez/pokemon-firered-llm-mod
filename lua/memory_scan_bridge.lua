-- memory_scan_bridge.lua — Minimal bridge for memory scanning
-- Pokemon FireRed (NOT REV 1) on mGBA 0.10+
--
-- RESPONSIBILITIES:
--   - TCP client that connects to Python server
--   - Respond to PING, READ, FIND commands
--   - Let Python scan GBA memory remotely
--
-- DOES NOT:
--   - Detect dialog events
--   - Inject / write to game memory
--   - Collect fingerprints or stream per-frame data
--
-- Usage:
--   1. python -m python.main  (select memory scan)
--   2. mGBA → Tools → Scripting → Load → lua/memory_scan_bridge.lua
--   3. Use the Python interactive CLI to scan memory

-- Path resolution
local SCRIPT_DIR = debug.getinfo(1, "S").source:match("@?(.*)[/\\]") or "."
local LIB = SCRIPT_DIR .. "/lib"

-- Load library modules
local cfg      = dofile(LIB .. "/config.lua")
local utils    = dofile(LIB .. "/utils.lua")
local ipc      = dofile(LIB .. "/ipc.lua")
local commands = dofile(LIB .. "/commands.lua")

-- Initialise modules
utils.set_log_level(cfg.LOG_LEVEL)
ipc.init(cfg, utils, "scanner")
commands.init(cfg, utils, ipc)

-- Register commands
commands.register_all()   -- READ + FIND

--  FRAME CALLBACK

callbacks:add("frame", function()
  ipc.tick()
end)

--  STARTUP

console:log("─────────────────────────────────────────────────────")
console:log("  memory_scan_bridge.lua — READ/FIND only")
console:log("  Commands: PING, READ, FIND")
console:log("  Target:   " .. cfg.HOST .. ":" .. cfg.PORT)
console:log("  Protocol: v" .. cfg.PROTO_VERSION)
console:log("─────────────────────────────────────────────────────")

ipc.try_connect()
