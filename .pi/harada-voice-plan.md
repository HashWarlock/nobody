# Harada Voice Agent — Integration Plan

## Concept

One hotkey. You press `Cmd+Shift+T`, speak to nobody as your Harada coach, release, and:
1. Your speech is transcribed
2. The LLM responds as your Harada coach **with tool access** to read/write your goal data
3. The response is spoken back to you
4. A **dashboard overlay** (Hammerspoon webview) appears showing your progress and the live conversation

Nobody IS your Harada coach. You just talk to it like a person:
- "Hey, I finished my exercise today" → agent checks off the habit, says congrats
- "How am I doing this week?" → agent pulls analytics, tells you verbally
- "I want to add a new goal about networking" → agent updates the OW64 chart
- "Let's do my evening reflection" → agent walks you through journaling via voice

---

## Current Architecture

```
Hammerspoon hotkey (Cmd+Shift+T)
    → Python main.py start (record audio)
    → Python main.py stop_and_process
        → STT (Whisper MLX) → transcript
        → LLM (RedPill API, OpenAI-compatible) → response text
        → TTS (Moshi MLX) → speak response
```

**Key facts:**
- Each hotkey press spawns a new Python process
- Conversation history persists in-memory within `stop_and_process` (loaded from file)
- LLM call is plain `chat/completions` — **no tool calling yet**
- RedPill API is OpenAI-compatible, so it supports tool calling
- Persona system already supports switching system prompts

---

## Target Architecture

```
Hammerspoon hotkey (Cmd+Shift+T — same as today)
    │
    ├─ Persona set to "harada" (Cmd+Shift+5 or auto-detect)
    │
    → Python main.py start (record audio)
    → Python main.py stop_and_process
        → STT → transcript
        │
        → LLM chat/completions WITH tools:
        │   tools = [harada_habits, harada_goals, harada_journal, harada_progress]
        │   │
        │   ├─ If LLM calls a tool → execute tool (read/write JSON)
        │   │   → feed result back to LLM
        │   │   → LLM produces final text response
        │   │
        │   └─ If no tool call → just a text response
        │
        → TTS → speak response
        → Write conversation + state to IPC file
        → Signal Hammerspoon to update overlay
    │
Hammerspoon (parallel)
    → webview overlay shows:
        - conversation transcript (user said / agent said)
        - harada dashboard (goals, habits, streaks, progress)
        - updates after each exchange
```

---

## Implementation Steps

### Step 1: Add Tool Calling to LLM Router

**File: `llm_router.py`**

Add a `chat_with_tools()` method that:
1. Sends `tools` definitions in the OpenAI format
2. Handles `tool_calls` in the response
3. Executes tool functions locally
4. Feeds results back to the LLM in a loop until it produces a final text response

```python
def chat_with_tools(self, llm_config, messages, system_prompt, tools, tool_executor):
    """Chat with tool calling support.
    
    Loop:
    1. Call LLM with messages + tools
    2. If response has tool_calls → execute each, append results, goto 1
    3. If response is text → return it
    """
```

The RedPill API (OpenAI-compatible) supports `tools` parameter with `type: "function"` definitions.

### Step 2: Harada Tool Functions

**File: `harada_tools.py`** (new)

Python functions that read/write the `.pi/harada/*.json` files. Same data format as the pi extension, so both systems work on the same data.

```python
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_habit",
            "description": "Mark a habit as done for today",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_name": {"type": "string", "description": "Partial name match of the habit"}
                },
                "required": ["habit_name"]
            }
        }
    },
    # ... list_habits, uncheck_habit, get_progress, write_journal,
    #     complete_action, get_goal_form, etc.
]

def execute_tool(name: str, arguments: dict) -> str:
    """Execute a harada tool and return result as string."""
```

Tools are intentionally **simpler and more natural-language friendly** than the pi extension tools, since they're used via voice:
- `check_habit(habit_name)` — fuzzy match, not exact ID
- `list_habits()` — today's habits with status
- `get_progress()` — full snapshot in natural language
- `write_journal(went_well, didnt_go_well, learnings, mood, energy)` 
- `complete_action(goal_number, action_number)` — mark OW64 action done
- `get_goals()` — show north star and supporting goals

### Step 3: Harada Persona

**File: `personas.yaml`** — add entry:

```yaml
harada:
    name: "Harada Coach"
    hotkey: "cmd+shift+5"
    llm:
      provider: "redpill"
      model: "moonshotai/kimi-k2.5"
    voice: "default"
    enable_tools: true              # new field — tells main.py to use chat_with_tools
    tools: "harada"                 # new field — which tool set to load
    system_prompt: |
      You are a warm, encouraging Harada Method coach speaking via voice.
      
      Core identity:
      - You are "nobody" — a personal coach who uses the Harada Method
      - Speak naturally, conversationally — this is voice, not text
      - Be concise — 2-3 sentences per response unless asked for detail
      - Use the tools to read and update the user's actual data
      - Never make up data — always call the tools to check
      
      Your tools give you access to:
      - The user's north star goal and OW64 chart
      - Daily habit tracking (check/uncheck habits by name)
      - Journal entries (help them reflect)
      - Progress analytics (streaks, completion rates, trends)
      
      Behavior:
      - When they say they did something → call check_habit
      - When they ask about progress → call get_progress
      - When they want to reflect → guide them and call write_journal
      - Always use actual data from tools, never guess
      - Celebrate wins with genuine warmth
      - On setbacks, be curious not judgmental
      - Remind them of their affirmation when appropriate
      - Keep responses SHORT for voice — this is spoken aloud
```

### Step 4: Update `main.py` Stop-and-Process Flow

Modify `handle_stop_and_process()`:

```python
def handle_stop_and_process():
    # ... existing STT code ...
    
    persona = persona_manager.get_current()
    
    # Check if persona uses tools
    if persona.get("enable_tools") and persona.get("tools") == "harada":
        from harada_tools import TOOL_DEFINITIONS, execute_tool
        response = conversation.get_response_with_tools(
            tools=TOOL_DEFINITIONS,
            tool_executor=execute_tool
        )
    else:
        response = conversation.get_response()
    
    # Write state for overlay
    write_overlay_state(transcript, response)
    
    # ... existing TTS code ...
```

### Step 5: Overlay State File (Python → Hammerspoon IPC)

**File: `/tmp/claude/voice-realtime/harada-overlay.json`**

After each exchange, Python writes:

```json
{
    "timestamp": "2026-02-12T00:30:00",
    "conversation": [
        {"role": "user", "text": "I finished my exercise today"},
        {"role": "assistant", "text": "Nice! I've checked off your exercise habit. That's 3 out of 5 for today. Keep it going!"}
    ],
    "dashboard": {
        "northStar": "Become a senior ML engineer by Dec 2026",
        "daysSinceStart": 47,
        "daysRemaining": 187,
        "affirmation": "I am becoming a Senior ML Engineer...",
        "habits": [
            {"name": "Study ML paper", "done": true},
            {"name": "Exercise", "done": true},
            {"name": "Coding practice", "done": false},
            {"name": "Journal", "done": false},
            {"name": "Network", "done": true}
        ],
        "habitsCompleted": 3,
        "habitsTotal": 5,
        "streak": 23,
        "ow64Completion": 53,
        "goalProgress": [
            {"id": 1, "title": "ML Fundamentals", "pct": 75},
            ...
        ],
        "avgMood": 3.8,
        "avgEnergy": 3.5
    }
}
```

### Step 6: Hammerspoon Dashboard Overlay

**File: `harada-overlay.lua`** (loaded from `hotkeys.lua`)

A `hs.webview` overlay that:
1. Watches `/tmp/claude/voice-realtime/harada-overlay.json` via `hs.pathwatcher`
2. Renders a dashboard + conversation as HTML
3. Appears when the harada persona is active and a conversation happens
4. Stays visible between exchanges, updating after each one
5. Can be dismissed with Escape or clicking X

```
┌─────────────────────────────────────────────┐
│  🎯 HARADA COACH                        ✕   │
│─────────────────────────────────────────────│
│                                             │
│  ⭐ Become a senior ML engineer by Dec 2026 │
│  📅 Day 47 / 234  │  🔥 23-day streak      │
│                                             │
│  ┌─ TODAY'S HABITS ──────────────────────┐  │
│  │  ✅ Study ML paper                    │  │
│  │  ✅ Exercise                          │  │
│  │  ☐  Coding practice                  │  │
│  │  ☐  Journal                          │  │
│  │  ✅ Network                           │  │
│  │                          3/5 (60%)    │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  OW64: ████████░░░░░░░░░░ 53%  [34/64]     │
│  30d Rate: 78%  │  Mood: 3.8  │  ⚡ 3.5    │
│                                             │
│─────── CONVERSATION ────────────────────────│
│                                             │
│  🎤 "I finished my exercise today"          │
│                                             │
│  🤖 "Nice! I've checked off your exercise   │
│     habit. That's 3 out of 5 for today.     │
│     Keep it going!"                          │
│                                             │
│  🎤 "How's my week looking?"                │
│                                             │
│  🤖 "You're at a 78% habit rate this week,  │
│     up from 72% last week. Your ML study    │
│     streak is solid at 23 days..."          │
│                                             │
└─────────────────────────────────────────────┘
```

The overlay is a positioned `hs.webview` with:
- Semi-transparent dark background
- Auto-positions to right side of screen (not blocking work)
- Smooth appearance/disappearance
- Updates reactively when the JSON file changes
- HTML/CSS rendered dashboard (webview supports full web rendering)

### Step 7: Wire It All Together in `hotkeys.lua`

```lua
-- Existing Cmd+Shift+T works exactly the same
-- When persona is "harada", the Python side uses tools
-- After each exchange, Python writes overlay state
-- Hammerspoon pathwatcher detects change, updates webview

-- New: Cmd+Shift+5 to switch to Harada persona
hs.hotkey.bind({"cmd", "shift"}, "5", function()
    hs.alert.show("🎯 Harada Coach", 1)
    runCommand({MAIN_SCRIPT, "persona", "harada"})
    showHaradaOverlay()  -- show/bring up the overlay
end)
```

---

## File Changes Summary

| File | Change |
|------|--------|
| `llm_router.py` | Add `chat_with_tools()` method with tool call loop |
| `conversation.py` | Add `get_response_with_tools()` that delegates to router |
| `harada_tools.py` | **New** — tool definitions + executor (reads/writes .pi/harada/*.json) |
| `personas.yaml` | Add `harada` persona with `enable_tools: true` |
| `main.py` | Modify `stop_and_process` to use tools when persona enables them; write overlay state |
| `harada_overlay.lua` | **New** — Hammerspoon webview overlay with dashboard + conversation |
| `hotkeys.lua` | Add `Cmd+Shift+5` for harada persona; load overlay module |

---

## Data Compatibility

The Python `harada_tools.py` reads/writes the **same JSON files** in `.pi/harada/` as the pi extension. Both can coexist:
- **Voice (this integration):** Talk to nobody → tools read/write JSON → overlay shows dashboard
- **Text (pi extension):** Use pi in terminal → same tools read/write same JSON → TUI overlay shows dashboard

Same data, two interfaces. Your voice conversations and pi sessions see the same habits, goals, and progress.

---

## User Experience Flow

1. Press `Cmd+Shift+5` → switches to Harada Coach persona, overlay appears
2. Press and hold `Cmd+Shift+T` → "Good morning, I'm ready for my check-in"
3. Release → Agent responds: "Good morning! Your affirmation today is... You have 5 habits to complete. Yesterday you hit 4 out of 5. What's your plan for today?"
4. Overlay updates: shows habits, progress, conversation transcript
5. Hold `Cmd+Shift+T` → "I already did my exercise and studied my ML paper"
6. Release → Agent calls `check_habit("exercise")`, `check_habit("ML paper")`, responds: "Awesome, 2 down! That's 23 days straight for ML study. 3 more to go today."
7. Overlay updates: habits checked off, streak incremented
8. Continue naturally... evening: "Let's do my reflection" → agent walks you through journaling
9. Press Escape or switch persona to dismiss overlay

**It's just one hotkey** — the same `Cmd+Shift+T` you already use. The only addition is `Cmd+Shift+5` to switch to the Harada persona (just like switching to any other persona).
