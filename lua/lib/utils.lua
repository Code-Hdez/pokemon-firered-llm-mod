-- utils.lua — Shared utility functions for mGBA bridge scripts
--
-- Hex conversion, JSON serialisation helpers, memory read/write,
-- and levelled logging.  Every other Lua module depends on this.

local M = {}

-- Hex formatting

function M.to_hex(n)
  if n == nil then return "nil" end
  return string.format("0x%08X", n)
end

function M.parse_hex(s)
  if not s then return nil end
  s = s:gsub("^0[xX]", "")
  return tonumber(s, 16)
end

function M.bytes_to_hexstr(raw)
  if not raw then return "" end
  local t = {}
  for i = 1, #raw do
    t[i] = string.format("%02X", raw:byte(i))
  end
  return table.concat(t)
end

-- JSON helpers

function M.json_escape(str)
  if not str then return "" end
  return (str
    :gsub("\\", "\\\\")
    :gsub('"',  '\\"')
    :gsub("\n", "\\n")
    :gsub("\r", "\\r")
    :gsub("\t", "\\t"))
end

-- Memory access

function M.read32(addr)
  local b0 = emu:read8(addr)
  local b1 = emu:read8(addr + 1)
  local b2 = emu:read8(addr + 2)
  local b3 = emu:read8(addr + 3)
  return b0 + b1 * 256 + b2 * 65536 + b3 * 16777216
end

function M.read16(addr)
  return emu:read8(addr) + emu:read8(addr + 1) * 256
end

function M.is_rom_ptr(val)
  return val >= 0x08000000 and val < 0x0A000000
end

function M.is_ewram_ptr(val)
  return val >= 0x02000000 and val <= 0x0203FFFF
end

-- Levelled logging

local log_level = 2   -- default: INFO

function M.set_log_level(level)
  log_level = level
end

function M.log_error(tag, msg)
  if log_level >= 1 then
    console:log("[" .. tag .. "] ERROR: " .. msg)
  end
end

function M.log_info(tag, msg)
  if log_level >= 2 then
    console:log("[" .. tag .. "] " .. msg)
  end
end

function M.log_debug(tag, msg)
  if log_level >= 3 then
    console:log("[" .. tag .. "] (dbg) " .. msg)
  end
end

return M
