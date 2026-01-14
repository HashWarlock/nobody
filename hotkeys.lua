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

-- Start listening (called on key press)
function voiceRealtime.startListening()
    runCommand({MAIN_SCRIPT, "start"})
    notify("Voice", "Listening...")
end

-- Stop listening and process (called on key release)
function voiceRealtime.stopListening()
    runCommand({MAIN_SCRIPT, "stop_and_process"})
    notify("Voice", "Processing...")
end

-- Stop conversation completely (Cmd+Shift+X)
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
-- Push-to-talk: fn+Space (press to start, release to stop and process)
local pushToTalk = hs.hotkey.new({"fn"}, "space",
    voiceRealtime.startListening,  -- pressedFn
    voiceRealtime.stopListening    -- releasedFn
)
pushToTalk:enable()

-- Other controls
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
