-- Harada Method - Hammerspoon Integration
-- Invoke the pi agent from hotkeys for habit tracking, check-ins, and dashboard
--
-- Three integration modes:
--   1. Direct JSON reads (instant, no agent) — for status/dashboard
--   2. pi print mode (one-shot agent) — for quick queries
--   3. pi RPC mode (persistent agent) — for interactive sessions
--
-- Hotkeys:
--   Cmd+Shift+H  — Show habit status (chooser with check/uncheck)
--   Cmd+Shift+G  — Quick Harada status notification
--   Cmd+Shift+J  — Open pi in terminal for journal/check-in
--   Cmd+Shift+N  — Open pi dashboard in terminal (interactive)

local HOME = os.getenv("HOME")
local PROJECT_DIR = HOME .. "/Projects/AI/nobody"
local HARADA_DIR = PROJECT_DIR .. "/.pi/harada"
local PI_EXTENSION = PROJECT_DIR .. "/.pi/extensions/harada-method/src/index.ts"

-- Use nvm-managed node/pi
local NODE_BIN = HOME .. "/.nvm/versions/node/v22.18.0/bin"
local PI_BIN = NODE_BIN .. "/pi"

-- ============================================================
-- Mode 1: Direct JSON reads (instant, no agent needed)
-- ============================================================

-- Read and parse a JSON file
local function readJson(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    local ok, data = pcall(hs.json.decode, content)
    if ok then return data end
    return nil
end

-- Get today's date as YYYY-MM-DD
local function today()
    return os.date("%Y-%m-%d")
end

-- Read current Harada state directly from JSON files
local function getHaradaState()
    local goalForm = readJson(HARADA_DIR .. "/goal-form.json")
    local habits = readJson(HARADA_DIR .. "/habits.json") or {}
    local habitLog = readJson(HARADA_DIR .. "/habit-log.json") or {}
    local todayLog = habitLog[today()] or {}

    -- Filter active habits
    local activeHabits = {}
    for _, h in ipairs(habits) do
        if h.active then
            table.insert(activeHabits, h)
        end
    end

    -- Count completions
    local completed = 0
    for _, h in ipairs(activeHabits) do
        if todayLog[h.id] == true then
            completed = completed + 1
        end
    end

    return {
        goalForm = goalForm,
        habits = activeHabits,
        habitLog = habitLog,
        todayLog = todayLog,
        completed = completed,
        total = #activeHabits,
    }
end

-- ============================================================
-- Mode 2: pi print mode (one-shot agent queries)
-- ============================================================

-- Run pi in print mode with the harada extension
-- Callback receives (exitCode, stdout, stderr)
local function piQuery(prompt, callback)
    local env = {
        PATH = NODE_BIN .. ":" .. os.getenv("PATH"),
        HOME = HOME,
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or "",
    }

    local task = hs.task.new(PI_BIN, callback, {
        "-p",                             -- print mode
        "-e", PI_EXTENSION,               -- load harada extension
        "--no-session",                   -- don't persist session
        prompt
    })

    -- Set environment
    task:setEnvironment(env)
    task:setWorkingDirectory(PROJECT_DIR)
    task:start()
    return task
end

-- ============================================================
-- Mode 3: pi RPC mode (persistent agent)
-- ============================================================

local rpcProcess = nil
local rpcPendingCallbacks = {}  -- id -> callback

-- Start persistent RPC agent (call once)
local function startRpcAgent()
    if rpcProcess and rpcProcess:isRunning() then return end

    local env = {
        PATH = NODE_BIN .. ":" .. os.getenv("PATH"),
        HOME = HOME,
        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or "",
    }

    rpcProcess = hs.task.new(PI_BIN, nil, function(task, stdOut, stdErr)
        -- Stream callback - processes each line of stdout
        if stdOut then
            for line in stdOut:gmatch("[^\n]+") do
                local ok, event = pcall(hs.json.decode, line)
                if ok and event then
                    -- Handle responses
                    if event.type == "response" and event.id then
                        local cb = rpcPendingCallbacks[event.id]
                        if cb then
                            rpcPendingCallbacks[event.id] = nil
                            cb(event)
                        end
                    end

                    -- Handle streaming text
                    if event.type == "message_update" then
                        local delta = event.assistantMessageEvent
                        if delta and delta.type == "text_delta" then
                            -- Could accumulate text for display
                        end
                    end
                end
            end
        end
        return true  -- keep streaming
    end, {
        "--mode", "rpc",
        "-e", PI_EXTENSION,
        "--no-session",
    })

    rpcProcess:setEnvironment(env)
    rpcProcess:setWorkingDirectory(PROJECT_DIR)
    rpcProcess:start()
end

-- Send an RPC command
local function rpcSend(command, callback)
    if not rpcProcess or not rpcProcess:isRunning() then
        startRpcAgent()
        -- Brief delay for startup
        hs.timer.doAfter(2, function()
            rpcSend(command, callback)
        end)
        return
    end

    local id = hs.host.uuid()
    command.id = id
    if callback then
        rpcPendingCallbacks[id] = callback
    end

    local json = hs.json.encode(command) .. "\n"
    rpcProcess:setInput(json)
end

-- Send a prompt via RPC and get the final response text
local function rpcPrompt(message, callback)
    local responseText = ""

    -- We need to track text via events, not just the response
    -- For simplicity, use print mode for one-shots instead
    rpcSend({ type = "prompt", message = message }, function(resp)
        if callback then callback(resp) end
    end)
end

-- ============================================================
-- Hotkey: Cmd+Shift+G — Quick status notification
-- ============================================================

hs.hotkey.bind({"cmd", "shift"}, "G", function()
    local state = getHaradaState()

    if not state.goalForm then
        hs.alert.show("🎯 No Harada goal set up yet\nRun /harada-setup in pi", 3)
        return
    end

    -- Build status text
    local lines = {}
    table.insert(lines, "⭐ " .. (state.goalForm.northStar or ""))

    if state.total > 0 then
        table.insert(lines, string.format("✅ Habits: %d/%d", state.completed, state.total))
    end

    if state.goalForm.affirmation and state.goalForm.affirmation ~= "" then
        table.insert(lines, "💫 " .. state.goalForm.affirmation)
    end

    -- Calculate days
    if state.goalForm.deadline and state.goalForm.deadline ~= "" then
        local y, m, d = state.goalForm.deadline:match("(%d+)-(%d+)-(%d+)")
        if y then
            local deadline = os.time({year=tonumber(y), month=tonumber(m), day=tonumber(d)})
            local daysLeft = math.ceil((deadline - os.time()) / 86400)
            if daysLeft > 0 then
                table.insert(lines, string.format("📅 %d days remaining", daysLeft))
            end
        end
    end

    hs.alert.show(table.concat(lines, "\n"), 4)
end)

-- ============================================================
-- Hotkey: Cmd+Shift+H — Habit checker (chooser UI)
-- ============================================================

hs.hotkey.bind({"cmd", "shift"}, "H", function()
    local state = getHaradaState()

    if state.total == 0 then
        hs.alert.show("📋 No habits set up\nUse pi to add habits", 3)
        return
    end

    -- Build chooser items
    local choices = {}
    for _, h in ipairs(state.habits) do
        local done = state.todayLog[h.id] == true
        local mark = done and "✅ " or "☐  "
        table.insert(choices, {
            text = mark .. h.name,
            subText = h.frequency .. (done and " (done)" or " (tap to toggle)"),
            habitId = h.id,
            isDone = done,
            habitName = h.name,
        })
    end

    -- Add status row at top
    table.insert(choices, 1, {
        text = string.format("📊 %d/%d habits done today", state.completed, state.total),
        subText = state.goalForm and ("⭐ " .. state.goalForm.northStar) or "",
        habitId = nil,
    })

    local chooser = hs.chooser.new(function(choice)
        if not choice or not choice.habitId then return end

        -- Toggle the habit directly in the JSON
        local log = readJson(HARADA_DIR .. "/habit-log.json") or {}
        local todayStr = today()
        if not log[todayStr] then log[todayStr] = {} end

        local newVal = not choice.isDone
        log[todayStr][choice.habitId] = newVal

        -- Write back atomically
        local tmpPath = HARADA_DIR .. "/habit-log.json.tmp"
        local outPath = HARADA_DIR .. "/habit-log.json"
        local f = io.open(tmpPath, "w")
        if f then
            f:write(hs.json.encode(log, true))
            f:close()
            os.rename(tmpPath, outPath)
        end

        local status = newVal and "✅" or "↩️"
        hs.alert.show(status .. " " .. choice.habitName, 1.5)

        -- Recount and show updated status
        local newState = getHaradaState()
        if newState.completed == newState.total and newState.total > 0 then
            hs.alert.show("🎉 All habits complete!", 2)
        end
    end)

    chooser:choices(choices)
    chooser:placeholderText("Toggle a habit...")
    chooser:show()
end)

-- ============================================================
-- Hotkey: Cmd+Shift+J — Open pi for journal/check-in
-- ============================================================

hs.hotkey.bind({"cmd", "shift"}, "J", function()
    -- Open a new terminal window with pi + harada extension
    local script = string.format([[
        tell application "Terminal"
            activate
            do script "cd '%s' && export PATH='%s:$PATH' && pi -e '%s' '/reflect'"
        end tell
    ]], PROJECT_DIR, NODE_BIN, PI_EXTENSION)

    hs.osascript.applescript(script)
    hs.alert.show("📓 Opening journal...", 1.5)
end)

-- ============================================================
-- Hotkey: Cmd+Shift+N — Open pi dashboard (interactive)
-- ============================================================

hs.hotkey.bind({"cmd", "shift"}, "N", function()
    local script = string.format([[
        tell application "Terminal"
            activate
            do script "cd '%s' && export PATH='%s:$PATH' && pi -e '%s'"
        end tell
    ]], PROJECT_DIR, NODE_BIN, PI_EXTENSION)

    hs.osascript.applescript(script)
    hs.alert.show("🎯 Opening Harada agent...", 1.5)
end)

-- ============================================================
-- Hotkey: Cmd+Shift+A — AI-powered habit insight (print mode)
-- ============================================================

hs.hotkey.bind({"cmd", "shift"}, "A", function()
    local state = getHaradaState()
    if not state.goalForm then
        hs.alert.show("🎯 No Harada goal set up", 2)
        return
    end

    hs.alert.show("🤔 Getting insight...", 1.5)

    piQuery("Use harada_progress with action 'insights' and give me a brief 2-3 sentence coaching nudge. Be concise.", function(exitCode, stdOut, stdErr)
        if exitCode == 0 and stdOut and stdOut ~= "" then
            -- Trim and show
            local text = stdOut:gsub("^%s+", ""):gsub("%s+$", "")
            if #text > 300 then text = text:sub(1, 300) .. "..." end
            hs.alert.show("💡 " .. text, 8)
        else
            hs.alert.show("❌ Agent error", 2)
        end
    end)
end)

-- ============================================================
-- Menubar indicator (optional persistent display)
-- ============================================================

local haradaMenu = hs.menubar.new()

local function updateMenubar()
    local state = getHaradaState()

    if not state.goalForm then
        haradaMenu:setTitle("🎯")
        haradaMenu:setMenu({
            { title = "No Harada goal set up", disabled = true },
            { title = "-" },
            { title = "Open pi to set up", fn = function()
                hs.osascript.applescript(string.format([[
                    tell application "Terminal"
                        activate
                        do script "cd '%s' && export PATH='%s:$PATH' && pi -e '%s' '/harada-setup'"
                    end tell
                ]], PROJECT_DIR, NODE_BIN, PI_EXTENSION))
            end },
        })
        return
    end

    -- Show completion in menubar
    if state.total > 0 then
        haradaMenu:setTitle(string.format("🎯 %d/%d", state.completed, state.total))
    else
        haradaMenu:setTitle("🎯")
    end

    -- Build menu
    local menuItems = {
        { title = "⭐ " .. (state.goalForm.northStar or ""), disabled = true },
        { title = "-" },
    }

    -- Habits
    for _, h in ipairs(state.habits) do
        local done = state.todayLog[h.id] == true
        local mark = done and "✅ " or "☐  "
        table.insert(menuItems, {
            title = mark .. h.name,
            fn = function()
                -- Toggle habit
                local log = readJson(HARADA_DIR .. "/habit-log.json") or {}
                local todayStr = today()
                if not log[todayStr] then log[todayStr] = {} end
                log[todayStr][h.id] = not done
                local tmpPath = HARADA_DIR .. "/habit-log.json.tmp"
                local outPath = HARADA_DIR .. "/habit-log.json"
                local f = io.open(tmpPath, "w")
                if f then
                    f:write(hs.json.encode(log, true))
                    f:close()
                    os.rename(tmpPath, outPath)
                end
                updateMenubar()
            end
        })
    end

    table.insert(menuItems, { title = "-" })
    table.insert(menuItems, { title = "📓 Journal / Check-in", fn = function()
        hs.osascript.applescript(string.format([[
            tell application "Terminal"
                activate
                do script "cd '%s' && export PATH='%s:$PATH' && pi -e '%s' '/reflect'"
            end tell
        ]], PROJECT_DIR, NODE_BIN, PI_EXTENSION))
    end })
    table.insert(menuItems, { title = "🎯 Open Dashboard", fn = function()
        hs.osascript.applescript(string.format([[
            tell application "Terminal"
                activate
                do script "cd '%s' && export PATH='%s:$PATH' && pi -e '%s'"
            end tell
        ]], PROJECT_DIR, NODE_BIN, PI_EXTENSION))
    end })
    table.insert(menuItems, { title = "💡 Get AI Insight", fn = function()
        hs.alert.show("🤔 Thinking...", 1.5)
        piQuery("Use harada_progress insights. Give a brief coaching nudge in 2 sentences.", function(exitCode, stdOut)
            if exitCode == 0 and stdOut then
                hs.alert.show("💡 " .. stdOut:gsub("^%s+", ""):gsub("%s+$", ""):sub(1, 300), 8)
            end
        end)
    end })

    haradaMenu:setMenu(menuItems)
end

-- Refresh menubar every 5 minutes
updateMenubar()
local menubarTimer = hs.timer.doEvery(300, updateMenubar)

-- ============================================================
-- Cleanup on reload
-- ============================================================

local function cleanup()
    if rpcProcess and rpcProcess:isRunning() then
        rpcProcess:terminate()
    end
    if menubarTimer then menubarTimer:stop() end
end

-- Register cleanup for hs.reload()
hs.shutdownCallback = cleanup

hs.alert.show("🎯 Harada hotkeys loaded!", 2)
