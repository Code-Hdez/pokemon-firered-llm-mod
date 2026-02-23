-- dialog.lua — AND-gate dialog detection FSM
--
-- Detects dialog open / close / page-wait / page-advance events by
-- combining three conditions every frame:
--   1. engine_state ≥ 1  (script engine active)
--   2. buffer snapshot changed  (first BUF_SNAP_LEN bytes differ)
--   3. 0xFF (EOS) found within TEXT_BUF_MAX bytes  AND  len ≥ 2
--
-- Strictly read-only — never writes to game memory.
-- Event delivery is via callbacks set by the entry script.

local M = {}

local cfg       -- config table   (injected via M.init)
local utils     -- utils module   (injected via M.init)
local TAG = "DIALOG"

-- FSM constants
M.IDLE       = 0
M.DISPLAYING = 1
M.WAIT_INPUT = 2

-- Internal state
local state            = 0
local prev_buf_snap    = ""
local prev_engine_st   = 0
local last_open_frame  = -999

-- Callbacks (nil until set by entry script)
local on_open          = nil   -- fn(info_table)
local on_close         = nil   -- fn()
local on_page_wait     = nil   -- fn()
local on_page_advance  = nil   -- fn(text_hex | nil)

-- Init

function M.init(config, utils_mod)
  cfg   = config
  utils = utils_mod
end

-- Callback registration

function M.on_dialog_open(fn)    on_open         = fn end
function M.on_dialog_close(fn)   on_close        = fn end
function M.on_page_wait(fn)      on_page_wait    = fn end
function M.on_page_advance(fn)   on_page_advance = fn end

-- Buffer helpers (local)

local function buf_snapshot()
  local ok, raw = pcall(function()
    return emu:readRange(cfg.TEXT_BUF, cfg.BUF_SNAP_LEN)
  end)
  if ok and raw and type(raw) == "string" then
    return raw
  end
  -- Fallback: byte-by-byte read (some mGBA builds)
  local t = {}
  for i = 0, cfg.BUF_SNAP_LEN - 1 do
    t[#t + 1] = string.char(emu:read8(cfg.TEXT_BUF + i))
  end
  return table.concat(t)
end

local function buf_has_eos()
  local data = emu:readRange(cfg.TEXT_BUF, cfg.TEXT_BUF_MAX)
  for i = 1, #data do
    if data:byte(i) == 0xFF then
      return true, i - 1   -- text_len = bytes before EOS
    end
  end
  return false, 0
end

-- Public buffer reader

function M.read_buf_hex()
  local data = emu:readRange(cfg.TEXT_BUF, cfg.TEXT_BUF_MAX)
  local t = {}
  for i = 1, #data do
    local b = data:byte(i)
    t[#t + 1] = string.format("%02X", b)
    if b == 0xFF then break end
  end
  return table.concat(t)
end

-- State accessors

function M.get_state()
  return state
end

function M.get_engine_state()
  return emu:read8(cfg.STATE_ADDR)
end

-- Snapshot refresh (call after injection to avoid re-trigger)

function M.refresh_snapshot()
  prev_buf_snap = buf_snapshot()
end

-- Reset (call once at startup)

function M.reset()
  state           = M.IDLE
  prev_buf_snap   = buf_snapshot()
  prev_engine_st  = 0
  last_open_frame = -999
end

-- Per-frame tick

function M.tick()
  local engine_state = emu:read8(cfg.STATE_ADDR)
  local cur_snap     = buf_snapshot()

  -- IDLE → detect new dialog
  if state == M.IDLE then
    if engine_state >= 1 and cur_snap ~= prev_buf_snap then
      local has_eos, text_len = buf_has_eos()
      if has_eos and text_len >= 2 then
        local frame = emu:currentFrame()
        if (frame - last_open_frame) >= cfg.DEBOUNCE_FRAMES then
          last_open_frame = frame

          local npc_ptr = utils.read32(cfg.NPC_SCRIPT_PTR)
          local cmd_ptr = utils.read32(cfg.SCRIPT_CMD_PTR)
          local text_hex = M.read_buf_hex()

          state = M.DISPLAYING

          if on_open then
            on_open({
              npc_ptr      = npc_ptr,
              cmd_ptr      = cmd_ptr,
              text_hex     = text_hex,
              text_len     = text_len,
              engine_state = engine_state,
              frame        = frame,
              npc_is_rom   = utils.is_rom_ptr(npc_ptr),
              cmd_is_rom   = utils.is_rom_ptr(cmd_ptr),
            })
          end
        end
      end
    end

  -- DISPLAYING → page-wait or close
  elseif state == M.DISPLAYING then
    if engine_state == 2 then
      state = M.WAIT_INPUT
      if on_page_wait then on_page_wait() end
    elseif engine_state == 0 then
      state = M.IDLE
      if on_close then on_close() end
    end

  -- WAIT_INPUT → page-advance or close
  elseif state == M.WAIT_INPUT then
    if engine_state == 1 then
      state = M.DISPLAYING
      local text_hex = nil
      if cur_snap ~= prev_buf_snap then
        local has_eos, tlen = buf_has_eos()
        if has_eos and tlen >= 2 then
          text_hex = M.read_buf_hex()
        end
      end
      if on_page_advance then on_page_advance(text_hex) end
    elseif engine_state == 0 then
      state = M.IDLE
      if on_close then on_close() end
    end
  end

  prev_engine_st = engine_state
  prev_buf_snap  = cur_snap
end

return M
