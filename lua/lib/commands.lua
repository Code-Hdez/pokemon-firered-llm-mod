-- commands.lua — Reusable IPC command handlers (READ, FIND)
--
-- Registers common memory-access commands on the IPC module.
-- Each entry script calls the register_* helpers it needs.

local M = {}

local cfg     -- config table
local utils   -- utils module
local ipc     -- ipc module

-- Init

function M.init(config, utils_mod, ipc_mod)
  cfg   = config
  utils = utils_mod
  ipc   = ipc_mod
end

-- READ <hex_addr> <len>

function M.register_read()
  ipc.on_command("READ", function(parts, cmd_id)
    local addr = utils.parse_hex(parts[2])
    local len  = tonumber(parts[3] or "0") or 0
    if not addr or len <= 0 then
      ipc.send_json(ipc.make_response(
        '"type":"err","msg":"usage: READ <hexaddr> <len>"', cmd_id))
      return
    end
    local data = emu:readRange(addr, len)
    local hex  = utils.bytes_to_hexstr(data)
    ipc.send_json(ipc.make_response(string.format(
      '"type":"read","addr":"%s","len":%d,"hex":"%s"',
      utils.to_hex(addr), len, hex
    ), cmd_id))
  end)
end

-- FIND <hex_pattern> [start_addr] [end_addr]

function M.register_find()
  ipc.on_command("FIND", function(parts, cmd_id)
    local hex_pat    = parts[2] or ""
    local start_addr = utils.parse_hex(parts[3]) or cfg.EWRAM_START
    local end_addr   = utils.parse_hex(parts[4]) or cfg.EWRAM_END

    -- Parse pattern bytes
    local pat = {}
    for i = 1, #hex_pat, 2 do
      local val = tonumber(hex_pat:sub(i, i + 1), 16)
      if not val then
        ipc.send_json(ipc.make_response(
          '"type":"err","msg":"bad hex in FIND pattern"', cmd_id))
        return
      end
      pat[#pat + 1] = val
    end
    if #pat == 0 then
      ipc.send_json(ipc.make_response(
        '"type":"err","msg":"usage: FIND <hex> [start] [end]"', cmd_id))
      return
    end

    -- Scan memory
    local range_len = end_addr - start_addr + 1
    local data      = emu:readRange(start_addr, range_len)
    local results   = {}

    for i = 1, #data - #pat + 1 do
      local match = true
      for j = 1, #pat do
        if data:byte(i + j - 1) ~= pat[j] then
          match = false
          break
        end
      end
      if match then
        results[#results + 1] = utils.to_hex(start_addr + i - 1)
        if #results >= cfg.MAX_FIND_RESULTS then break end
      end
    end

    -- Build JSON array
    local arr = "["
    for i, a in ipairs(results) do
      if i > 1 then arr = arr .. "," end
      arr = arr .. '"' .. a .. '"'
    end
    arr = arr .. "]"

    ipc.send_json(ipc.make_response(string.format(
      '"type":"find","pattern":"%s","start":"%s","end":"%s","count":%d,"addrs":%s',
      utils.json_escape(hex_pat),
      utils.to_hex(start_addr),
      utils.to_hex(end_addr),
      #results, arr
    ), cmd_id))
  end)
end

-- Convenience: register everything

function M.register_all()
  M.register_read()
  M.register_find()
end

return M
