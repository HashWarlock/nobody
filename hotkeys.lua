-- Voice Realtime - Hammerspoon Hotkey Configuration
-- Provides hotkeys for conversation control and persona switching

local voiceRealtime = {}

-- Configuration
local PYTHON = os.getenv("HOME") .. "/voice-env/bin/python"
local SCRIPT_DIR = os.getenv("HOME") .. "/voice-realtime"
local MAIN_SCRIPT = SCRIPT_DIR .. "/main.py"
local TEMP_DIR = "/tmp/claude/voice-realtime"

-- State tracking
local conversationTask = nil

-- Helper function to show notification
local function notify(title, text)
    hs.notify.new({title = title, informativeText = text}):send()
end

-- Helper function to run command
local function runCommand(args)
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 then
            print("Error: " .. (stdErr or "unknown"))
        end
    end, args)
    task:start()
    return task
end

-- Toggle conversation (Cmd+Shift+D)
function voiceRealtime.toggle()
    runCommand({MAIN_SCRIPT, "toggle"})
    notify("Voice", "Toggle")
end

-- Stop conversation (Cmd+Shift+X)
function voiceRealtime.stop()
    runCommand({MAIN_SCRIPT, "stop"})
    notify("Voice", "Stopped")
end

-- Switch persona functions
function voiceRealtime.switchAssistant()
    runCommand({MAIN_SCRIPT, "persona", "assistant"})
    notify("Persona", "Assistant")
end

function voiceRealtime.switchTutor()
    runCommand({MAIN_SCRIPT, "persona", "tutor"})
    notify("Persona", "Tutor")
end

function voiceRealtime.switchCreative()
    runCommand({MAIN_SCRIPT, "persona", "creative"})
    notify("Persona", "Creative Partner")
end

function voiceRealtime.switchCasual()
    runCommand({MAIN_SCRIPT, "persona", "casual"})
    notify("Persona", "Buddy")
end

-- Bind hotkeys
hs.hotkey.bind({"cmd", "shift"}, "D", voiceRealtime.toggle)
hs.hotkey.bind({"cmd", "shift"}, "X", voiceRealtime.stop)
hs.hotkey.bind({"cmd", "shift"}, "1", voiceRealtime.switchAssistant)
hs.hotkey.bind({"cmd", "shift"}, "2", voiceRealtime.switchTutor)
hs.hotkey.bind({"cmd", "shift"}, "3", voiceRealtime.switchCreative)
hs.hotkey.bind({"cmd", "shift"}, "4", voiceRealtime.switchCasual)

-- Reload config (Cmd+Shift+R)
hs.hotkey.bind({"cmd", "shift"}, "R", function()
    hs.reload()
    notify("Hammerspoon", "Config reloaded")
end)

hs.alert.show("Voice Realtime loaded")

return voiceRealtime
