-- ipc.lua — TCP client for the mGBA ↔ Python bridge
--
-- Manages a single TCP connection: connect, reconnect, send, receive.
-- Dispatches incoming newline-delimited commands to registered handlers.
-- Built-in command: PING (always available).
--
-- Protocol notes:
--   Lua → Python :  JSON lines  (events, responses)
--   Python → Lua :  plain-text commands, one per line
--     Optional trailing  #<id>  on any command → echoed back in response
--
-- Thread-safety: n/a (single-threaded mGBA callback environment).

local M = {}

local cfg           -- config table   (injected via M.init)
local utils         -- utils module   (injected via M.init)
local TAG = "IPC"

-- Connection state
local client             = nil
local rx_buf             = ""
local retry_countdown    = 0
local command_handlers   = {}   -- CMD_NAME → handler(parts, cmd_id)
local mode_name          = "unknown"

-- Initialisation

function M.init(config, utils_mod, mode)
  cfg       = config
  utils     = utils_mod
  mode_name = mode or "unknown"
  utils.set_log_level(cfg.LOG_LEVEL)
end

-- Connection management

function M.is_connected()
  return client ~= nil
end

function M.send_json(json_str)
  if not client then return false end
  local ok, result, err = pcall(function()
    return client:send(json_str .. "\n")
  end)
  if not ok then
    utils.log_error(TAG, "send pcall: " .. tostring(result))
    return false
  end
  if not result then
    utils.log_error(TAG, "send: " .. tostring(err))
    return false
  end
  return true
end

--- Alias kept for readability in entry scripts.
M.send_event = M.send_json

function M.try_connect()
  local sock, err = socket.connect(cfg.HOST, cfg.PORT)
  if not sock then return false end

  client          = sock
  rx_buf          = ""
  retry_countdown = 0
  utils.log_info(TAG, "Connected to " .. cfg.HOST .. ":" .. cfg.PORT)

  -- handshake: include protocol version + mode
  local title = emu:getGameTitle() or ""
  local code  = emu:getGameCode()  or ""
  M.send_json(string.format(
    '{"type":"hello","proto":%d,"title":"%s","code":"%s","mode":"%s"}',
    cfg.PROTO_VERSION,
    utils.json_escape(title),
    utils.json_escape(code),
    utils.json_escape(mode_name)
  ))
  return true
end

function M.disconnect()
  utils.log_info(TAG, "Disconnected")
  if client then
    pcall(function() client:close() end)
  end
  client = nil
  rx_buf = ""
end

-- Command registration

function M.on_command(cmd_name, handler)
  command_handlers[cmd_name:upper()] = handler
end

-- Response builder 
-- Builds a JSON object string and optionally appends an "id" field.
--   fields_str :  everything between the outer braces, e.g.
--                 '"type":"pong"'
--   cmd_id     :  optional command id (string or nil)

function M.make_response(fields_str, cmd_id)
  local j = "{" .. fields_str
  if cmd_id then
    j = j .. ',"id":"' .. utils.json_escape(cmd_id) .. '"'
  end
  return j .. "}"
end

-- Internal: command parsing + dispatch

local function dispatch_command(line)
  -- Extract optional trailing #<id>
  local cmd_id = nil
  local body   = line
  local id_match = line:match("%s+#(%S+)%s*$")
  if id_match then
    cmd_id = id_match
    body   = line:gsub("%s+#%S+%s*$", "")
  end

  local parts = {}
  for w in body:gmatch("%S+") do parts[#parts + 1] = w end
  local cmd = (parts[1] or ""):upper()
  if cmd == "" then return end

  -- Built-in: PING
  if cmd == "PING" then
    M.send_json(M.make_response('"type":"pong"', cmd_id))
    return
  end

  -- Registered handler
  local handler = command_handlers[cmd]
  if handler then
    handler(parts, cmd_id)
    return
  end

  -- Unknown
  M.send_json(M.make_response(
    '"type":"err","msg":"unknown command: ' .. utils.json_escape(cmd) .. '"',
    cmd_id
  ))
end

-- Internal: non-blocking RX pump

local function pump_rx()
  if not client then return end

  local ok, chunk = pcall(function()
    if client.receive then return client:receive(4096) end
    if client.read    then return client:read(4096)    end
    return nil
  end)

  if not ok then
    utils.log_error(TAG, "receive: " .. tostring(chunk))
    M.disconnect()
    return
  end

  if chunk and type(chunk) == "string" and #chunk > 0 then
    rx_buf = rx_buf .. chunk
    -- Guard against unbounded growth (4× max message size)
    if #rx_buf > cfg.MAX_MSG_SIZE * 4 then
      utils.log_error(TAG, "rx_buf overflow — flushing")
      rx_buf = ""
    end
  end

  -- Process all complete lines
  while true do
    local nl = rx_buf:find("\n", 1, true)
    if not nl then break end
    local line = rx_buf:sub(1, nl - 1):gsub("\r$", "")
    rx_buf = rx_buf:sub(nl + 1)
    if #line > 0 and #line <= cfg.MAX_MSG_SIZE then
      dispatch_command(line)
    end
  end
end

-- Per-frame tick (call from frame callback)

function M.tick()
  if not client then
    retry_countdown = retry_countdown + 1
    if retry_countdown >= cfg.CONNECT_RETRY_FRAMES then
      retry_countdown = 0
      M.try_connect()
    end
    return
  end
  pump_rx()
end

return M
