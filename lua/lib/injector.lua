-- injector.lua — Write Pokemon-encoded text to the EWRAM text buffer
--
-- Validates the hex payload, writes each byte, ensures EOS terminator,
-- and zero-fills the remainder of the buffer for safety.
--
-- Does NOT depend on dialog.lua or ipc.lua — pure memory writer.

local M = {}

local cfg     -- config table   (injected via M.init)
local utils   -- utils module   (injected via M.init)
local TAG = "INJECT"

-- Init

function M.init(config, utils_mod)
  cfg   = config
  utils = utils_mod
end

-- Write text to buffer
-- hex_string : uppercase hex characters  (e.g. "C2E3E0D5FF")
-- Returns     : ok (bool), reason (string)

function M.write_text(hex_string)
  -- Block if script engine is in WAIT_INPUT state
  local es = emu:read8(cfg.STATE_ADDR)
  if es == 2 then
    utils.log_info(TAG, "BLOCKED — state=2 WAIT_INPUT")
    return false, "wait_input"
  end

  -- Validate payload
  if not hex_string or #hex_string < 2 then
    utils.log_info(TAG, "BLOCKED — empty payload")
    return false, "empty"
  end
  if #hex_string % 2 ~= 0 then
    utils.log_info(TAG, "BLOCKED — odd hex length (" .. #hex_string .. ")")
    return false, "odd_length"
  end
  if hex_string:match("[^0-9A-Fa-f]") then
    utils.log_info(TAG, "BLOCKED — invalid hex characters")
    return false, "bad_hex"
  end

  local byte_count = #hex_string / 2
  if byte_count > cfg.MAX_INJECT_SIZE then
    utils.log_info(TAG, string.format(
      "BLOCKED — too large (%d > %d)", byte_count, cfg.MAX_INJECT_SIZE))
    return false, "too_large"
  end

  -- Write bytes to TEXT_BUF
  local addr      = cfg.TEXT_BUF
  local last_byte = 0

  for i = 1, #hex_string, 2 do
    local hb  = hex_string:sub(i, i + 1)
    local val = tonumber(hb, 16)
    if not val then
      utils.log_error(TAG, "bad hex at pos " .. i .. ": " .. hb)
      return false, "bad_hex"
    end
    emu:write8(addr, val)
    last_byte = val
    addr = addr + 1
  end

  -- Ensure EOS terminator
  if last_byte ~= 0xFF then
    emu:write8(addr, 0xFF)
    addr = addr + 1
  end

  -- Zero-fill remainder
  while addr < cfg.TEXT_BUF + cfg.TEXT_BUF_MAX do
    emu:write8(addr, 0x00)
    addr = addr + 1
  end

  utils.log_info(TAG, string.format(
    "OK — %d bytes → %s", byte_count, utils.to_hex(cfg.TEXT_BUF)))
  return true, "ok"
end

return M
