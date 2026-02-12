---
name: harada-build
description: >
  Build macro for the Harada Method voice agent integration. Implements the
  plan to make nobody a Harada coach you talk to with one hotkey, with a
  Hammerspoon webview overlay showing progress and conversation.
  Use /skill:harada-build to execute the build pipeline.
---

# Harada Voice Agent — Build Macro

Read the full plan first:
```bash
cat .pi/harada-voice-plan.md
```

## Pre-flight

Verify the project structure:
```bash
ls main.py llm_router.py conversation.py persona_manager.py personas.yaml hotkeys.lua
ls .pi/harada/ 2>/dev/null || echo "No harada data yet (OK for first build)"
ls .pi/extensions/harada-method/src/data/types.ts  # data types reference
```

## Build Steps

### Step 1: `harada_tools.py` — Tool Functions

Create `harada_tools.py` in project root. This is the Python equivalent of the pi extension tools, reading/writing the same `.pi/harada/*.json` files.

Requirements:
- Read `.pi/harada-voice-plan.md` section "Step 2: Harada Tool Functions"
- Read `.pi/extensions/harada-method/src/data/types.ts` for the JSON data shapes
- Tool definitions in OpenAI function calling format
- Tools must be voice-friendly: fuzzy habit name matching, natural language output
- `execute_tool(name, arguments)` dispatcher function
- Tools: `list_habits`, `check_habit`, `uncheck_habit`, `get_progress`, `write_journal`, `read_journal`, `complete_action`, `get_goals`, `get_affirmation`
- All read/write from `{PROJECT_DIR}/.pi/harada/` directory
- Return human-readable strings (agent speaks these to the user)

### Step 2: `llm_router.py` — Add Tool Calling

Modify `llm_router.py` to add `chat_with_tools()`:

Requirements:
- Read `.pi/harada-voice-plan.md` section "Step 1: Add Tool Calling to LLM Router"
- New method `chat_with_tools(llm_config, messages, system_prompt, tools, tool_executor)`
- RedPill API is OpenAI-compatible: send `tools` param, handle `tool_calls` in response
- Loop: call LLM → if tool_calls, execute each, append tool results, call LLM again → until text response
- Max 5 tool call rounds to prevent infinite loops
- Existing `chat()` method unchanged (backward compatible)

### Step 3: `conversation.py` — Add Tool Support

Modify `conversation.py`:

Requirements:
- New method `get_response_with_tools(tools, tool_executor)`
- Calls `llm_router.chat_with_tools()` instead of `chat()`
- Tool call messages should NOT be stored in conversation history (only user + final assistant text)
- Everything else unchanged

### Step 4: `personas.yaml` — Add Harada Persona

Add `harada` entry:

Requirements:
- Read `.pi/harada-voice-plan.md` section "Step 3: Harada Persona" for the system prompt
- `enable_tools: true` and `tools: "harada"` fields
- Uses `moonshotai/kimi-k2.5` model (good at tool calling)
- System prompt emphasizes: voice mode, concise responses, always use tools for data, warm coaching

### Step 5: `main.py` — Wire Tools + Overlay State

Modify `handle_stop_and_process()`:

Requirements:
- Read `.pi/harada-voice-plan.md` section "Step 4" and "Step 5"
- When persona has `enable_tools` + `tools == "harada"`, import and use harada_tools
- After getting response, write overlay state to `/tmp/claude/voice-realtime/harada-overlay.json`
- Overlay state includes: conversation history, dashboard data (read from .pi/harada/*.json)
- Existing non-tool personas must work exactly the same (backward compatible)

### Step 6: `harada_overlay.lua` — Hammerspoon Dashboard Webview

Create `harada_overlay.lua`:

Requirements:
- Read `.pi/harada-voice-plan.md` section "Step 6: Hammerspoon Dashboard Overlay"
- `hs.webview` positioned at right side of screen
- `hs.pathwatcher` on `/tmp/claude/voice-realtime/harada-overlay.json`
- When file changes → reload data → update HTML
- HTML/CSS dashboard showing: north star, habits with checkmarks, OW64 progress bar, streaks, mood/energy, conversation transcript
- Dark theme, semi-transparent, rounded corners
- Dismiss with Escape or X button
- Functions: `showHaradaOverlay()`, `hideHaradaOverlay()`, `updateHaradaOverlay()`

### Step 7: `hotkeys.lua` — Add Persona Hotkey + Load Overlay

Modify `hotkeys.lua`:

Requirements:
- Add `Cmd+Shift+5` to switch to harada persona and show overlay
- Load `harada_overlay.lua` at bottom (same pattern as existing code)
- When switching away from harada persona, optionally hide overlay

### Step 8: Integration Test

1. Switch to harada persona: `Cmd+Shift+5`
2. Verify overlay appears (may be empty if no data yet)
3. Push-to-talk: "Help me set up my north star goal"
4. Verify agent responds via voice with coaching guidance
5. Push-to-talk: "My north star is to become a senior ML engineer by December 2026"
6. Verify agent calls tools, overlay updates with goal
7. Push-to-talk: "What habits should I track daily?"
8. Verify conversation appears in overlay
9. Switch to another persona: `Cmd+Shift+1` — verify voice works normally without tools

### Step 9: Git Commit

```bash
git add harada_tools.py harada_overlay.lua llm_router.py conversation.py main.py personas.yaml hotkeys.lua
git commit -m "feat: integrate Harada coach into voice pipeline with dashboard overlay

- Add tool calling support to LLM router (OpenAI function calling)
- Add harada_tools.py with voice-friendly tool functions
- Add harada persona with coaching system prompt
- Add Hammerspoon webview overlay showing progress + conversation
- One hotkey: Cmd+Shift+T (push-to-talk, same as always)
- Cmd+Shift+5 to switch to Harada coach persona"
```

## Key Principles

1. **One hotkey** — Cmd+Shift+T is the only interaction. Just talk.
2. **Voice-first** — tool output is spoken, not displayed as text. Keep responses SHORT.
3. **Same data** — reads/writes .pi/harada/*.json, compatible with pi extension.
4. **Backward compatible** — all existing personas and hotkeys work unchanged.
5. **Overlay is passive** — it shows up and updates, but all interaction is voice.
