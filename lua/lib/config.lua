-- config.lua — Shared configuration for all mGBA bridge scripts
-- Pokemon FireRed US (NOT REV 1)
--
-- This file is the SINGLE SOURCE OF TRUTH for addresses, ports,
-- and tuning constants. Every Lua module reads from here.

local Config = {}

-- Network
Config.HOST = "127.0.0.1"
Config.PORT = 35600

-- Protocol
Config.PROTO_VERSION   = 2
Config.MAX_MSG_SIZE    = 8192   -- Max bytes per IPC message
Config.MAX_INJECT_SIZE = 256    -- Max Pokemon-encoded bytes to write

-- Text buffer (EWRAM)
Config.TEXT_BUF     = 0x02021D18  -- Primary text display buffer
Config.TEXT_BUF_MAX = 256         -- Safe write region (to 0x02021E17)

-- Script engine (IWRAM)
Config.STATE_ADDR      = 0x03000EB0  -- 0=IDLE  1=ACTIVE  2=WAIT
Config.SCRIPT_CMD_PTR  = 0x03000EB8  -- Script command pointer (ROM)
Config.NPC_SCRIPT_PTR  = 0x03000EBC  -- NPC/event script data pointer

-- Map detection (gSaveBlock1Ptr)
Config.SAVE_BLOCK1_PTR = 0x03005008  -- IWRAM → EWRAM pointer
Config.MAP_GROUP_OFF   = 4           -- SaveBlock1 + 4  (u8)
Config.MAP_NUM_OFF     = 5           -- SaveBlock1 + 5  (u8)

-- Memory scan defaults
Config.EWRAM_START = 0x02000000
Config.EWRAM_END   = 0x0203FFFF

-- Timing / thresholds
Config.CONNECT_RETRY_FRAMES = 60    -- Frames between TCP reconnect tries
Config.DEBOUNCE_FRAMES      = 10    -- Min frames between dialog_open events
Config.BUF_SNAP_LEN         = 32    -- Bytes for buffer-change detection
Config.MAX_FIND_RESULTS      = 64   -- Cap on FIND command results

-- Logging
-- 0 = OFF,  1 = ERROR,  2 = INFO,  3 = DEBUG
Config.LOG_LEVEL = 2

return Config
