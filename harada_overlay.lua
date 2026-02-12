-- Harada Method Dashboard Overlay for Hammerspoon
--
-- A webview overlay that shows Harada progress + conversation.
-- Updates reactively when the Python voice agent writes new state.
--
-- API:
--   showHaradaOverlay()   — show or bring to front
--   hideHaradaOverlay()   — dismiss
--   toggleHaradaOverlay() — toggle visibility

local HOME = os.getenv("HOME")
local OVERLAY_STATE_FILE = "/tmp/claude/voice-realtime/harada-overlay.json"

-- Webview and watcher references
local haradaWebview = nil
local haradaWatcher = nil
local haradaVisible = false

-- ── HTML Template ──────────────────────────────────────

local function buildHTML(data)
    local dashboard = data and data.dashboard or {}
    local conversation = data and data.conversation or {}

    local northStar = dashboard.northStar or "No goal set up yet"
    local affirmation = dashboard.affirmation or ""
    local streak = dashboard.streak or 0
    local daysSince = dashboard.daysSinceStart or 0
    local daysLeft = dashboard.daysRemaining or -1
    local habitsCompleted = dashboard.habitsCompleted or 0
    local habitsTotal = dashboard.habitsTotal or 0
    local habits = dashboard.habits or {}
    local ow64Pct = dashboard.ow64Completion or 0
    local ow64Done = dashboard.ow64Done or 0
    local ow64Total = dashboard.ow64Total or 0
    local goalProgress = dashboard.goalProgress or {}
    local avgMood = dashboard.avgMood
    local avgEnergy = dashboard.avgEnergy

    -- Build habits HTML
    local habitsHTML = ""
    for _, h in ipairs(habits) do
        local mark = h.done and "✅" or "☐"
        local cls = h.done and "done" or "pending"
        habitsHTML = habitsHTML .. string.format(
            '<div class="habit %s">%s %s</div>\n', cls, mark, h.name
        )
    end
    if #habits == 0 then
        habitsHTML = '<div class="habit pending">No habits set up yet</div>'
    end

    -- Build goal progress HTML
    local goalsHTML = ""
    for _, g in ipairs(goalProgress) do
        goalsHTML = goalsHTML .. string.format(
            [[<div class="goal-row">
                <span class="goal-label">%d. %s</span>
                <div class="progress-bar"><div class="progress-fill" style="width:%d%%"></div></div>
                <span class="goal-pct">%d%%</span>
            </div>]], g.id, g.title, g.pct, g.pct
        )
    end

    -- Build conversation HTML
    local convHTML = ""
    for _, msg in ipairs(conversation) do
        if msg.role == "user" then
            convHTML = convHTML .. string.format(
                '<div class="msg user"><span class="icon">🎤</span><span class="text">%s</span></div>\n',
                msg.text:gsub("<", "&lt;"):gsub(">", "&gt;")
            )
        else
            convHTML = convHTML .. string.format(
                '<div class="msg assistant"><span class="icon">🤖</span><span class="text">%s</span></div>\n',
                msg.text:gsub("<", "&lt;"):gsub(">", "&gt;")
            )
        end
    end
    if #conversation == 0 then
        convHTML = '<div class="msg assistant"><span class="icon">🎯</span><span class="text">Press Cmd+Shift+T to talk to your Harada coach</span></div>'
    end

    -- Timeline info
    local timelineStr = ""
    if daysSince > 0 then
        timelineStr = string.format("📅 Day %d", daysSince)
        if daysLeft > 0 then
            timelineStr = timelineStr .. string.format(" / %d total", daysSince + daysLeft)
        end
    end
    if streak > 0 then
        if timelineStr ~= "" then timelineStr = timelineStr .. "  │  " end
        timelineStr = timelineStr .. string.format("🔥 %d-day streak", streak)
    end

    -- Stats line
    local statsLine = ""
    if avgMood then statsLine = statsLine .. string.format("😊 Mood: %.1f/5  ", avgMood) end
    if avgEnergy then statsLine = statsLine .. string.format("⚡ Energy: %.1f/5", avgEnergy) end

    -- Habits fraction
    local habitsFrac = ""
    if habitsTotal > 0 then
        local pct = math.floor(habitsCompleted / habitsTotal * 100)
        habitsFrac = string.format("%d/%d (%d%%)", habitsCompleted, habitsTotal, pct)
    end

    -- OW64 bar
    local ow64Bar = ""
    if ow64Total > 0 then
        ow64Bar = string.format("%d/%d actions (%d%%)", ow64Done, ow64Total, ow64Pct)
    end

    return string.format([[<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro", "Helvetica Neue", sans-serif;
    background: rgba(20, 20, 28, 0.94);
    color: #e0e0e8;
    font-size: 13px;
    line-height: 1.5;
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  .header {
    padding: 16px 20px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    flex-shrink: 0;
  }
  .header .title {
    font-size: 15px;
    font-weight: 700;
    color: #a78bfa;
    margin-bottom: 4px;
  }
  .header .north-star {
    font-size: 14px;
    color: #fbbf24;
    margin-bottom: 4px;
  }
  .header .timeline {
    font-size: 12px;
    color: #9ca3af;
  }
  .close-btn {
    position: absolute;
    top: 12px;
    right: 16px;
    background: none;
    border: none;
    color: #6b7280;
    font-size: 18px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }
  .close-btn:hover { color: #e0e0e8; background: rgba(255,255,255,0.1); }

  .dashboard {
    padding: 12px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    flex-shrink: 0;
    max-height: 55vh;
    overflow-y: auto;
  }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #9ca3af;
    margin: 8px 0 6px;
  }
  .habits-grid { margin-bottom: 8px; }
  .habit {
    padding: 3px 0;
    font-size: 13px;
  }
  .habit.done { color: #9ca3af; }
  .habit.pending { color: #e0e0e8; }
  .habits-summary {
    text-align: right;
    font-size: 12px;
    color: #9ca3af;
    margin-bottom: 8px;
  }

  .goal-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 3px 0;
    font-size: 12px;
  }
  .goal-label { flex: 1; color: #d1d5db; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .progress-bar {
    width: 80px;
    height: 6px;
    background: rgba(255,255,255,0.1);
    border-radius: 3px;
    overflow: hidden;
    flex-shrink: 0;
  }
  .progress-fill {
    height: 100%%;
    background: linear-gradient(90deg, #a78bfa, #7c3aed);
    border-radius: 3px;
    transition: width 0.3s;
  }
  .goal-pct { width: 32px; text-align: right; color: #9ca3af; font-size: 11px; }

  .ow64-summary {
    margin: 8px 0;
    font-size: 12px;
    color: #9ca3af;
  }
  .ow64-bar {
    width: 100%%;
    height: 8px;
    background: rgba(255,255,255,0.08);
    border-radius: 4px;
    overflow: hidden;
    margin: 4px 0;
  }
  .ow64-fill {
    height: 100%%;
    background: linear-gradient(90deg, #34d399, #059669);
    border-radius: 4px;
    transition: width 0.3s;
  }

  .stats {
    font-size: 12px;
    color: #9ca3af;
    margin: 6px 0;
  }

  .conversation {
    flex: 1;
    overflow-y: auto;
    padding: 12px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .conv-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #9ca3af;
    padding: 0 0 6px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    position: sticky;
    top: 0;
    background: rgba(20, 20, 28, 0.98);
    flex-shrink: 0;
  }
  .msg {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .msg .icon { flex-shrink: 0; font-size: 14px; margin-top: 1px; }
  .msg .text { font-size: 13px; line-height: 1.5; }
  .msg.user .text { color: #93c5fd; }
  .msg.assistant .text { color: #e0e0e8; }

  .affirmation {
    font-style: italic;
    color: #a78bfa;
    font-size: 12px;
    margin: 4px 0 0;
    opacity: 0.8;
  }
</style>
</head>
<body>
  <button class="close-btn" onclick="window.location='hammerspoon://haradaClose'">✕</button>

  <div class="header">
    <div class="title">🎯 HARADA COACH</div>
    <div class="north-star">⭐ %s</div>
    <div class="timeline">%s</div>
    %s
  </div>

  <div class="dashboard">
    <div class="section-title">Today's Habits</div>
    <div class="habits-grid">%s</div>
    <div class="habits-summary">%s</div>

    %s

    %s

    %s
  </div>

  <div class="conversation">
    <div class="conv-title">Conversation</div>
    %s
  </div>

  <script>
    // Auto-scroll conversation to bottom
    var conv = document.querySelector('.conversation');
    conv.scrollTop = conv.scrollHeight;
  </script>
</body>
</html>]],
        northStar:gsub("<", "&lt;"):gsub(">", "&gt;"),
        timelineStr,
        affirmation ~= "" and string.format('<div class="affirmation">💫 %s</div>', affirmation:gsub("<", "&lt;"):gsub(">", "&gt;")) or "",
        habitsHTML,
        habitsFrac,
        -- Goal progress section
        #goalProgress > 0 and ('<div class="section-title">Goal Progress</div>' .. goalsHTML) or "",
        -- OW64 bar
        ow64Total > 0 and string.format(
            '<div class="section-title">OW64 Progress</div><div class="ow64-bar"><div class="ow64-fill" style="width:%d%%"></div></div><div class="ow64-summary">%s</div>',
            ow64Pct, ow64Bar
        ) or "",
        -- Stats
        statsLine ~= "" and string.format('<div class="stats">%s</div>', statsLine) or "",
        convHTML
    )
end

-- ── Webview Management ──────────────────────────────────

local function getOverlayFrame()
    local screen = hs.screen.mainScreen():frame()
    local w = 380
    local h = math.min(screen.h - 80, 700)
    return hs.geometry.rect(screen.x + screen.w - w - 20, screen.y + 40, w, h)
end

local function loadOverlayData()
    local f = io.open(OVERLAY_STATE_FILE, "r")
    if not f then return nil end
    local content = f:read("*a")
    f:close()
    local ok, data = pcall(hs.json.decode, content)
    if ok then return data end
    return nil
end

local function updateOverlay()
    if not haradaWebview then return end
    local data = loadOverlayData()
    local html = buildHTML(data)
    haradaWebview:html(html)
end

function showHaradaOverlay()
    if haradaWebview and haradaVisible then
        updateOverlay()
        haradaWebview:show()
        return
    end

    local frame = getOverlayFrame()
    haradaWebview = hs.webview.new(frame, {developerExtrasEnabled = false})
        :windowStyle({"titled", "closable", "nonactivating", "utility"})
        :level(hs.drawing.windowLevels.floating)
        :alpha(0.95)
        :allowTextEntry(false)
        :allowNewWindows(false)
        :windowTitle("Harada Coach")
        :closeOnEscape(true)
        :deleteOnClose(false)

    -- Handle close button via URL scheme
    haradaWebview:urlCallback(function(scheme, host, params, fullURL)
        if host == "haradaClose" or host == "haradaclose" then
            hideHaradaOverlay()
        end
    end)

    updateOverlay()
    haradaWebview:show()
    haradaVisible = true

    -- Start file watcher for reactive updates
    if not haradaWatcher then
        local watchDir = "/tmp/claude/voice-realtime"
        -- Ensure directory exists
        os.execute("mkdir -p " .. watchDir)
        haradaWatcher = hs.pathwatcher.new(watchDir, function(paths, flagTables)
            for _, p in ipairs(paths) do
                if p:find("harada%-overlay%.json") then
                    -- Small delay to ensure write is complete
                    hs.timer.doAfter(0.1, updateOverlay)
                    break
                end
            end
        end)
        haradaWatcher:start()
    end
end

function hideHaradaOverlay()
    if haradaWebview then
        haradaWebview:hide()
        haradaVisible = false
    end
end

function toggleHaradaOverlay()
    if haradaVisible then
        hideHaradaOverlay()
    else
        showHaradaOverlay()
    end
end

-- ── Cleanup ─────────────────────────────────────────────

function cleanupHaradaOverlay()
    if haradaWatcher then
        haradaWatcher:stop()
        haradaWatcher = nil
    end
    if haradaWebview then
        haradaWebview:delete()
        haradaWebview = nil
    end
    haradaVisible = false
end
