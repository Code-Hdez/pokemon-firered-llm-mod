-- dialog.lua — AND-gate dialog detection FSM
--
-- Detects dialog open / close / page-wait / page-advance events by
-- combining three conditions every frame:
--   1. engine_state ≥ 1  (script engine active)
--   2. buffer snapshot changed  (first BUF_SNAP_LEN bytes differ)
--   3. 0xFF (EOS) found within TEXT_BUF_MAX bytes  AND  len ≥ 2
--
-- HYBRID MODE (intro/cutscene detection):
--   When INTRO_DETECT_ENABLED, a parallel path fires on_intro_text()
--   whenever the text buffer changes with engine_state == 0.
--   Uses content hashing to avoid false-positive re-triggers on
--   stale buffer data.  Catches the Oak intro and any other text
--   that bypasses the overworld script engine.
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

-- Intro detection state
local intro_enabled      = false
local prev_text_hash     = 0
local last_intro_frame   = -999

-- Callbacks (nil until set by entry script)
local on_open          = nil   -- fn(info_table)
local on_close         = nil   -- fn()
local on_page_wait     = nil   -- fn()
local on_page_advance  = nil   -- fn(text_hex | nil)
local on_intro_text    = nil   -- fn(info_table)  — buffer-only detection

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
function M.on_intro_text(fn)     on_intro_text   = fn end

-- Intro mode control

function M.set_intro_detect(enabled)
  intro_enabled = enabled
  utils.log_info(TAG, "Intro detection: " .. tostring(enabled))
end

function M.is_intro_detect()
  return intro_enabled
end

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

-- Content hash — deterministic hash of the text bytes (up to EOS).
-- Used to distinguish genuinely new text from stale buffer data.

local function text_content_hash()
  local data = emu:readRange(cfg.TEXT_BUF, cfg.TEXT_BUF_MAX)
  local h = 5381
  for i = 1, #data do
    local b = data:byte(i)
    if b == 0xFF then break end
    h = ((h * 33) + b) % 0x7FFFFFFF
  end
  return h
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
  prev_buf_snap  = buf_snapshot()
  prev_text_hash = text_content_hash()
end

-- Reset (call once at startup)

function M.reset()
  state             = M.IDLE
  prev_buf_snap     = buf_snapshot()
  prev_engine_st    = 0
  last_open_frame   = -999
  prev_text_hash    = text_content_hash()
  last_intro_frame  = -999
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

          -- Update intro hash so we don't re-fire after transition
          prev_text_hash = text_content_hash()

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

    -- INTRO / CUTSCENE detection (engine_state == 0, buffer changed)
    -- Fires when text appears in the buffer outside the script engine.
    -- Uses content hash to avoid re-triggering on stale data.
    if intro_enabled and engine_state == 0 and cur_snap ~= prev_buf_snap then
      local has_eos, text_len = buf_has_eos()
      if has_eos and text_len >= 2 then
        local hash = text_content_hash()
        if hash ~= prev_text_hash then
          prev_text_hash = hash
          local frame = emu:currentFrame()
          if (frame - last_intro_frame) >= (cfg.INTRO_DEBOUNCE_FRAMES or 15) then
            last_intro_frame = frame
            local text_hex = M.read_buf_hex()
            utils.log_info(TAG, string.format(
              "INTRO_TEXT detected len=%d frame=%d", text_len, frame))
            if on_intro_text then
              on_intro_text({
                text_hex     = text_hex,
                text_len     = text_len,
                engine_state = engine_state,
                frame        = frame,
              })
            end
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
