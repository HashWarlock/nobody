-- Voice Realtime - Hammerspoon Hotkey Configuration
-- Push-to-talk conversational AI with multiple personas

-- Auto-detect paths: look for voice-env in common locations
local HOME = os.getenv("HOME")
local function findPython()
    local candidates = {
        HOME .. "/voice-env/bin/python",           -- Default install location
        HOME .. "/.local/share/voice-realtime/venv/bin/python",
        "/opt/homebrew/bin/python3",               -- Homebrew fallback
        "/usr/local/bin/python3",                  -- Intel Mac fallback
    }
    for _, path in ipairs(candidates) do
        local f = io.open(path, "r")
        if f then
            f:close()
            return path
        end
    end
    return candidates[1]  -- Default even if not found (will error clearly)
end

local function findMainScript()
    -- Look for main.py relative to this Lua file's config, or common locations
    local candidates = {
        HOME .. "/voice-realtime/main.py",                    -- Symlink/clone location
        HOME .. "/Projects/AI/nobody/main.py",                -- Dev location
        HOME .. "/.local/share/voice-realtime/main.py",       -- XDG location
    }
    for _, path in ipairs(candidates) do
        local f = io.open(path, "r")
        if f then
            f:close()
            return path
        end
    end
    return candidates[1]
end

local PYTHON = findPython()
local MAIN_SCRIPT = findMainScript()

-- Run Python command
local function runCommand(args)
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 then
            hs.notify.new({title = "Voice Error", informativeText = stdErr or "Command failed"}):send()
        end
    end, args)
    task:start()
end

-- Run Python command and type output at cursor
local function runCommandAndType(args)
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 then
            hs.notify.new({title = "Voice Error", informativeText = stdErr or "Command failed"}):send()
            return
        end
        if stdOut and stdOut ~= "" then
            -- Trim whitespace
            local text = stdOut:gsub("^%s+", ""):gsub("%s+$", "")
            if text ~= "" then
                -- Copy to clipboard and paste using AppleScript
                hs.pasteboard.setContents(text)
                hs.timer.doAfter(0.2, function()
                    hs.osascript.applescript('tell application "System Events" to keystroke "v" using command down')
                end)
            else
                hs.alert.show("Empty text", 1)
            end
        else
            hs.alert.show("No transcription", 1)
        end
    end, args)
    task:start()
end

-- Push-to-dictate: Cmd+Shift+D (hold to speak, release to type at cursor)
local pushToDictate = hs.hotkey.new({"cmd", "shift"}, "D",
    function()
        hs.alert.show("📝 Dictating...", 1)
        runCommand({MAIN_SCRIPT, "start"})
    end,
    function()
        hs.alert.show("⌨️ Typing...", 1)
        runCommandAndType({MAIN_SCRIPT, "dictate"})
    end
)
pushToDictate:enable()

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

-- Read selection aloud: Cmd+Shift+S
hs.hotkey.bind({"cmd", "shift"}, "S", function()
    -- Copy selected text
    hs.eventtap.keyStroke({"cmd"}, "c")
    -- Small delay to ensure clipboard is updated
    hs.timer.doAfter(0.1, function()
        local text = hs.pasteboard.getContents()
        if text and text ~= "" then
            hs.alert.show("🔊 Reading...", 1)
            runCommand({MAIN_SCRIPT, "speak", text})
        else
            hs.alert.show("No text selected", 1)
        end
    end)
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

-- Model chooser: Cmd+Shift+M
hs.hotkey.bind({"cmd", "shift"}, "M", function()
    -- Get models as JSON from Python
    local task = hs.task.new(PYTHON, function(exitCode, stdOut, stdErr)
        if exitCode ~= 0 or not stdOut or stdOut == "" then
            hs.alert.show("Failed to load models", 2)
            return
        end

        local ok, models = pcall(hs.json.decode, stdOut)
        if not ok or not models then
            hs.alert.show("Failed to parse models", 2)
            return
        end

        -- Build chooser choices
        local choices = {}
        for _, model in ipairs(models) do
            local text = model.name
            if model.current then
                text = "✓ " .. text
            end
            local subText = model.id .. " [" .. model.provider .. "]"
            if #model.features > 0 then
                subText = subText .. " - " .. table.concat(model.features, ", ")
            end
            table.insert(choices, {
                text = text,
                subText = subText,
                modelId = model.id,
                modelName = model.name
            })
        end

        -- Show chooser
        local chooser = hs.chooser.new(function(choice)
            if choice then
                hs.alert.show("🤖 " .. choice.modelName, 1)
                runCommand({MAIN_SCRIPT, "model", choice.modelId})
            end
        end)
        chooser:choices(choices)
        chooser:placeholderText("Select a model...")
        chooser:searchSubText(true)
        chooser:show()
    end, {MAIN_SCRIPT, "model_json"})
    task:start()
end)

-- Reload: Cmd+Shift+R
hs.hotkey.bind({"cmd", "shift"}, "R", function()
    hs.reload()
end)

-- ── Harada Coach ─────────────────────────────────────────

-- Derive project dir from MAIN_SCRIPT path
local PROJECT_DIR = MAIN_SCRIPT and MAIN_SCRIPT:match("(.+)/[^/]+$") or (HOME .. "/Projects/AI/nobody")

-- Load overlay module
local haradaOverlayPath = PROJECT_DIR .. "/harada_overlay.lua"
local haradaOverlayLoader, haradaOverlayErr = loadfile(haradaOverlayPath)
if haradaOverlayLoader then
    haradaOverlayLoader()
    print("Harada overlay loaded from: " .. haradaOverlayPath)
else
    print("Harada overlay not loaded: " .. (haradaOverlayErr or "file not found: " .. haradaOverlayPath))
end

-- Cmd+Shift+5: Switch to Harada Coach persona + show overlay
hs.hotkey.bind({"cmd", "shift"}, "5", function()
    hs.alert.show("🎯 Harada Coach", 1)
    runCommand({MAIN_SCRIPT, "persona", "harada"})
    if showHaradaOverlay then showHaradaOverlay() end
end)

hs.alert.show("Voice Realtime ready!", 2)
