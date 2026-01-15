-- Voice Realtime - Hammerspoon Hotkey Configuration
-- Push-to-talk conversational AI with multiple personas

local PYTHON = "/Users/hashwarlock/voice-env/bin/python"
local MAIN_SCRIPT = "/Users/hashwarlock/voice-realtime/main.py"

-- Run Python command
local function runCommand(args)
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 then
            hs.notify.new({title = "Voice Error", informativeText = stdErr or "Command failed"}):send()
        end
    end, args)
    task:start()
end

-- Push-to-talk: Cmd+Shift+T (hold to speak, release to process)
local pushToTalk = hs.hotkey.new({"cmd", "shift"}, "T",
    function()
        hs.alert.show("🎤 Listening...", 1)
        runCommand({MAIN_SCRIPT, "start"})
    end,
    function()
        hs.alert.show("🤖 Processing...", 1)
        runCommand({MAIN_SCRIPT, "stop_and_process"})
    end
)
pushToTalk:enable()

-- Stop: Cmd+Shift+X
hs.hotkey.bind({"cmd", "shift"}, "X", function()
    hs.alert.show("⏹ Stopped", 1)
    runCommand({MAIN_SCRIPT, "stop"})
end)

-- Persona switches
hs.hotkey.bind({"cmd", "shift"}, "1", function()
    hs.alert.show("👤 Assistant", 1)
    runCommand({MAIN_SCRIPT, "persona", "assistant"})
end)

hs.hotkey.bind({"cmd", "shift"}, "2", function()
    hs.alert.show("📚 Tutor", 1)
    runCommand({MAIN_SCRIPT, "persona", "tutor"})
end)

hs.hotkey.bind({"cmd", "shift"}, "3", function()
    hs.alert.show("🎨 Creative", 1)
    runCommand({MAIN_SCRIPT, "persona", "creative"})
end)

hs.hotkey.bind({"cmd", "shift"}, "4", function()
    hs.alert.show("😊 Casual", 1)
    runCommand({MAIN_SCRIPT, "persona", "casual"})
end)

-- Reload: Cmd+Shift+R
hs.hotkey.bind({"cmd", "shift"}, "R", function()
    hs.reload()
end)

hs.alert.show("Voice Realtime ready!", 2)
