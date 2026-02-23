-- fingerprint_collector.lua — Read-only dialog fingerprint collector
-- Pokemon FireRed (US (NOT REV 1)) on mGBA 0.10+
--
-- RESPONSIBILITIES:
--   - Detect dialog open/close/page events (via lib/dialog.lua)
--   - Read map group/num for zone detection
--   - Send JSON events to Python for classification & storage
--
-- DOES NOT:
--   - Write to game memory (strictly read-only)
--   - Inject text
--
-- Usage:
--   1. python -m python.main  (select fingerprint mode)
--   2. mGBA → Tools → Scripting → Load → lua/fingerprint_collector.lua
--   3. Walk around + interact — every dialog is captured

-- Path resolution
local SCRIPT_DIR = debug.getinfo(1, "S").source:match("@?(.*)[/\\]") or "."
local LIB = SCRIPT_DIR .. "/lib"

-- Load library modules
local cfg    = dofile(LIB .. "/config.lua")
local utils  = dofile(LIB .. "/utils.lua")
local ipc    = dofile(LIB .. "/ipc.lua")
local dialog = dofile(LIB .. "/dialog.lua")

-- Initialise modules
utils.set_log_level(cfg.LOG_LEVEL)
ipc.init(cfg, utils, "collector")
dialog.init(cfg, utils)

--  MAP DETECTION

local cur_map_group  = -1
local cur_map_num    = -1
local map_ever_valid = false

local function read_map()
  local sb1 = utils.read32(cfg.SAVE_BLOCK1_PTR)
  if not utils.is_ewram_ptr(sb1) then return -1, -1, false end
  local mg = emu:read8(sb1 + cfg.MAP_GROUP_OFF)
  local mn = emu:read8(sb1 + cfg.MAP_NUM_OFF)
  return mg, mn, true
end

local function check_map_change()
  local mg, mn, valid = read_map()
  if valid then
    map_ever_valid = true
    if mg ~= cur_map_group or mn ~= cur_map_num then
      cur_map_group = mg
      cur_map_num   = mn
      utils.log_info("MAP", string.format("MAP_CHANGE group=%d num=%d", mg, mn))
      ipc.send_json(string.format(
        '{"type":"map_change","map_group":%d,"map_num":%d,"map_valid":true}',
        mg, mn))
    end
  end
end

--  DIALOG EVENT HANDLERS

dialog.on_dialog_open(function(info)
  utils.log_info("COLLECTOR", string.format(
    "DIALOG_OPEN EBC=%s EB8=%s len=%d",
    utils.to_hex(info.npc_ptr), utils.to_hex(info.cmd_ptr), info.text_len))

  ipc.send_json(string.format(
    '{"type":"dialog_open","ptr_EBC":"%s","ptr_EB8":"%s","ebc_valid":%s,"eb8_valid":%s,"engine_state":%d,"textHex":"%s","text_len":%d,"frame":%d,"map_group":%d,"map_num":%d,"map_valid":%s}',
    utils.to_hex(info.npc_ptr),
    utils.to_hex(info.cmd_ptr),
    info.npc_is_rom and "true" or "false",
    info.cmd_is_rom and "true" or "false",
    info.engine_state,
    info.text_hex,
    info.text_len,
    info.frame,
    cur_map_group, cur_map_num,
    map_ever_valid and "true" or "false"))
end)

dialog.on_dialog_close(function()
  utils.log_info("COLLECTOR", "DIALOG_CLOSE")
  ipc.send_json(string.format(
    '{"type":"dialog_close","frame":%d}', emu:currentFrame()))
end)

dialog.on_page_wait(function()
  ipc.send_json(string.format(
    '{"type":"page_wait","frame":%d}', emu:currentFrame()))
end)

dialog.on_page_advance(function(text_hex)
  ipc.send_json(string.format(
    '{"type":"page_advance","textHex":"%s","frame":%d}',
    text_hex or "", emu:currentFrame()))
end)

--  IPC COMMANDS

-- MAP — return current map info
ipc.on_command("MAP", function(parts, cmd_id)
  local mg, mn, valid = read_map()
  ipc.send_json(ipc.make_response(string.format(
    '"type":"map_info","map_group":%d,"map_num":%d,"map_valid":%s',
    mg, mn, valid and "true" or "false"
  ), cmd_id))
end)

--  FRAME CALLBACK

callbacks:add("frame", function()
  ipc.tick()
  check_map_change()
  dialog.tick()
end)

--  STARTUP

dialog.reset()

console:log("─────────────────────────────────────────────────────")
console:log("  fingerprint_collector.lua — READ-ONLY mode")
console:log("  TEXT_BUF:   " .. utils.to_hex(cfg.TEXT_BUF))
console:log("  STATE_ADDR: " .. utils.to_hex(cfg.STATE_ADDR))
console:log("  Target:     " .. cfg.HOST .. ":" .. cfg.PORT)
console:log("  Protocol:   v" .. cfg.PROTO_VERSION)
console:log("─────────────────────────────────────────────────────")

ipc.try_connect()
