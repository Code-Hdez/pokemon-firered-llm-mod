-- dialog_injector.lua v3.0 — Dialog Detection + Text Injection
-- Pokemon FireRed (US (NOT REV 1)) on mGBA 0.10+
--
-- RESPONSIBILITIES:
--   - Detect dialog open/close/page events (via lib/dialog.lua)
--   - Write replacement text to text buffer (INJECT from Python)
--   - Optional manual injection mode (hardcoded test payload)
--   - Respond to PING, READ, FIND, INJECT, STREAM, WATCH commands
--
-- Usage:
--   1. python -m python.main  (select inject mode)
--   2. mGBA → Tools → Scripting → Load → lua/dialog_injector.lua
--   3. Talk to any NPC — text will be replaced by Python

-- Path resolution

local SCRIPT_DIR = debug.getinfo(1, "S").source:match("@?(.*)[/\\]") or "."
local LIB = SCRIPT_DIR .. "/lib"

-- Load library modules

local cfg      = dofile(LIB .. "/config.lua")
local utils    = dofile(LIB .. "/utils.lua")
local ipc      = dofile(LIB .. "/ipc.lua")
local dialog   = dofile(LIB .. "/dialog.lua")
local injector = dofile(LIB .. "/injector.lua")
local commands = dofile(LIB .. "/commands.lua")

-- Local config overrides
-- Set MANUAL_INJECT_ENABLED = true for standalone testing (no Python).

local MANUAL_INJECT_ENABLED = false
local MANUAL_INJECT_HEX =
  "C2E3E0D500BDD5E6E0E3E7B8FE"
  .. "D6DDD9E2EAD9E2DDD8E300D500D9E7E8D5FB"
  .. "E2E9D9EAD500D5EAD9E2E8E9E6D5ADFF"

-- Stream/Watch state (backward compat)

local stream_enabled  = false
local stream_every_n  = 2
local watch_flag_addr = nil
local watch_buf_addr  = nil
local watch_buf_len   = 0

-- Initialise modules

utils.set_log_level(cfg.LOG_LEVEL)
ipc.init(cfg, utils, "injector")
dialog.init(cfg, utils)
injector.init(cfg, utils)
commands.init(cfg, utils, ipc)

-- Enable intro/cutscene detection (Oak speech, etc.)
if cfg.INTRO_DETECT_ENABLED then
  dialog.set_intro_detect(true)
end

-- Injection state

local injection_done = false

--  DIALOG EVENT HANDLERS

dialog.on_dialog_open(function(info)
  local preview = info.text_hex:sub(1, 64)
  if #info.text_hex > 64 then preview = preview .. "..." end

  utils.log_info("DIALOG", string.format(
    "OPEN EBC=%s EB8=%s len=%d hex=%s",
    utils.to_hex(info.npc_ptr), utils.to_hex(info.cmd_ptr),
    info.text_len, preview))

  ipc.send_json(string.format(
    '{"type":"dialog_open","npc":"%s","ptr_EB8":"%s","ptr_EBC":"%s","textHex":"%s","len":%d,"frame":%d}',
    utils.to_hex(info.npc_ptr),
    utils.to_hex(info.cmd_ptr),
    utils.to_hex(info.npc_ptr),
    info.text_hex,
    info.text_len,
    info.frame))

  -- Manual injection (standalone test mode)
  if MANUAL_INJECT_ENABLED and not injection_done then
    utils.log_info("MANUAL", "Injecting hardcoded test message...")
    local ok, reason = injector.write_text(MANUAL_INJECT_HEX)
    if ok then
      dialog.refresh_snapshot()
      injection_done = true
      utils.log_info("MANUAL", "SUCCESS")
    else
      utils.log_error("MANUAL", "FAILED — " .. reason)
    end
  end
end)

dialog.on_dialog_close(function()
  utils.log_info("DIALOG", "CLOSE")
  ipc.send_json('{"type":"dialog_close"}')
  injection_done = false
end)

dialog.on_page_wait(function()
  utils.log_debug("DIALOG", "PAGE_WAIT")
  ipc.send_json('{"type":"dialog_page_wait"}')
end)

dialog.on_page_advance(function(text_hex)
  utils.log_debug("DIALOG", "PAGE_ADVANCE")
  ipc.send_json(string.format(
    '{"type":"dialog_page_advance","textHex":"%s"}',
    text_hex or ""))
end)

--  INTRO / CUTSCENE TEXT EVENT
--  Fires when text appears in the buffer while the overworld script
--  engine is idle (engine_state == 0).  Catches the Oak intro,
--  cutscenes, and any other non-script text.

dialog.on_intro_text(function(info)
  local preview = info.text_hex:sub(1, 64)
  if #info.text_hex > 64 then preview = preview .. "..." end

  utils.log_info("INTRO", string.format(
    "TEXT len=%d hex=%s", info.text_len, preview))

  -- Reset injection flag — this is a new message in the sequence
  injection_done = false

  ipc.send_json(string.format(
    '{"type":"intro_text","textHex":"%s","len":%d,"frame":%d}',
    info.text_hex, info.text_len, info.frame))

  -- Manual injection (standalone test mode)
  if MANUAL_INJECT_ENABLED and not injection_done then
    utils.log_info("MANUAL", "Injecting intro test message...")
    local ok, reason = injector.write_text(MANUAL_INJECT_HEX)
    if ok then
      dialog.refresh_snapshot()
      injection_done = true
      utils.log_info("MANUAL", "SUCCESS")
    else
      utils.log_error("MANUAL", "FAILED — " .. reason)
    end
  end
end)

--  IPC COMMANDS

-- READ & FIND (shared implementation)
commands.register_all()

-- INJECT <hex>
ipc.on_command("INJECT", function(parts, cmd_id)
  local hex_text = parts[2] or ""
  if #hex_text < 2 then
    ipc.send_json(ipc.make_response(
      '"type":"err","msg":"usage: INJECT <hex>"', cmd_id))
    return
  end
  if #hex_text % 2 ~= 0 then
    ipc.send_json(ipc.make_response(
      '"type":"err","msg":"INJECT hex must be even length"', cmd_id))
    return
  end
  if hex_text:match("[^0-9A-Fa-f]") then
    ipc.send_json(ipc.make_response(
      '"type":"err","msg":"INJECT hex has invalid characters"', cmd_id))
    return
  end

  local ok, reason = injector.write_text(hex_text:upper())
  if ok then
    dialog.refresh_snapshot()
    injection_done = true
    ipc.send_json(ipc.make_response(string.format(
      '"type":"ack","msg":"injected","len":%d', #hex_text / 2
    ), cmd_id))
  else
    ipc.send_json(ipc.make_response(string.format(
      '"type":"err","msg":"inject failed: %s"', utils.json_escape(reason)
    ), cmd_id))
  end
end)

-- STREAM ON [n] | STREAM OFF
ipc.on_command("STREAM", function(parts, cmd_id)
  local mode = (parts[2] or ""):upper()
  if mode == "ON" then
    stream_enabled = true
    local n = tonumber(parts[3] or "")
    if n and n >= 1 then stream_every_n = n end
    ipc.send_json(ipc.make_response(string.format(
      '"type":"ack","msg":"stream on","every":%d', stream_every_n
    ), cmd_id))
  else
    stream_enabled = false
    ipc.send_json(ipc.make_response(
      '"type":"ack","msg":"stream off"', cmd_id))
  end
end)

-- WATCH FLAG <addr> | WATCH BUF <addr> <len>
ipc.on_command("WATCH", function(parts, cmd_id)
  local which = (parts[2] or ""):upper()
  if which == "FLAG" then
    watch_flag_addr = utils.parse_hex(parts[3])
    ipc.send_json(ipc.make_response(string.format(
      '"type":"ack","msg":"watch flag","addr":"%s"',
      utils.to_hex(watch_flag_addr)
    ), cmd_id))
  elseif which == "BUF" then
    watch_buf_addr = utils.parse_hex(parts[3])
    watch_buf_len  = tonumber(parts[4] or "0") or 0
    ipc.send_json(ipc.make_response(string.format(
      '"type":"ack","msg":"watch buf","addr":"%s","len":%d',
      utils.to_hex(watch_buf_addr), watch_buf_len
    ), cmd_id))
  end
end)

--  STREAM TELEMETRY  (optional per-frame data)

local function maybe_stream()
  if not ipc.is_connected() or not stream_enabled then return end

  local frame = emu:currentFrame()
  if (frame % stream_every_n) ~= 0 then return end

  local flag_val = nil
  if watch_flag_addr then flag_val = emu:read8(watch_flag_addr) end

  local buf_hex = nil
  if watch_buf_addr and watch_buf_len > 0 then
    buf_hex = utils.bytes_to_hexstr(
      emu:readRange(watch_buf_addr, watch_buf_len))
  end

  local j = string.format(
    '{"type":"frame","frame":%d,"flag":%s,"flagAddr":"%s","bufAddr":"%s","bufLen":%d,"bufHex":"%s","detState":%d}',
    frame,
    (flag_val == nil) and "null" or tostring(flag_val),
    utils.to_hex(watch_flag_addr),
    utils.to_hex(watch_buf_addr),
    watch_buf_len or 0,
    utils.json_escape(buf_hex or ""),
    dialog.get_state())

  if not ipc.send_json(j) then
    ipc.disconnect()
  end
end

--  FRAME CALLBACK

callbacks:add("frame", function()
  ipc.tick()
  dialog.tick()
  maybe_stream()
end)

--  STARTUP

dialog.reset()

console:log("")
console:log("  dialog_injector.lua v3.1 — Detection + Injection + Intro")
console:log("  TEXT_BUF:       " .. utils.to_hex(cfg.TEXT_BUF))
console:log("  STATE_ADDR:     " .. utils.to_hex(cfg.STATE_ADDR))
console:log("  MANUAL_INJECT:  " .. tostring(MANUAL_INJECT_ENABLED))
console:log("  INTRO_DETECT:   " .. tostring(dialog.is_intro_detect()))
console:log("  Target:         " .. cfg.HOST .. ":" .. cfg.PORT)
console:log("  Protocol:       v" .. cfg.PROTO_VERSION)
console:log("")

ipc.try_connect()
