---
name: harada-build
description: >
  Build macro for the Harada Method extension. Implements the staged build plan
  step by step, with verification at each phase. Use /skill:harada-build to execute
  the build pipeline or resume from a specific step.
---

# Harada Method — Build Macro

This skill guides the implementation and testing of the Harada Method pi extension.
The extension is located at `.pi/extensions/harada-method/`.

## Pre-flight Check

Before building, verify the scaffold exists:

```bash
ls -la .pi/extensions/harada-method/src/
ls -la .pi/extensions/harada-method/src/data/
ls -la .pi/extensions/harada-method/src/tools/
ls -la .pi/extensions/harada-method/src/ui/
ls -la .pi/skills/harada-coach/SKILL.md
ls -la .pi/prompts/
```

Read the full implementation plan:
```bash
cat .pi/harada-method-plan.md
```

## Build Steps

Execute each step in order. After each step, verify by reading the created files and confirming they compile.

### Step 1: Verify Data Layer
Files should already exist:
- `src/data/types.ts` — All TypeScript interfaces
- `src/data/store.ts` — JSON persistence with atomic writes
- `src/data/analytics.ts` — Progress calculations (streaks, rates, completion)

Verification: Read each file. Ensure types are complete and analytics functions are pure.

### Step 2: Verify Tools
Files should already exist:
- `src/tools/goal-form.ts` — harada_goal_form tool
- `src/tools/ow64.ts` — harada_ow64 tool
- `src/tools/habits.ts` — harada_habits tool
- `src/tools/journal.ts` — harada_journal tool
- `src/tools/progress.ts` — harada_progress tool

Verification: Read each tool file. Ensure all actions are implemented and error handling is present.

### Step 3: Verify UI Overlays
Files should already exist:
- `src/ui/dashboard.ts` — Main dashboard overlay
- `src/ui/ow64-grid.ts` — OW64 mandala grid overlay
- `src/ui/habit-tracker.ts` — Habit tracker overlay with interactive checking

Verification: Read each UI file. Ensure they handle keyboard input and use theme properly.

### Step 4: Verify Extension Entry Point
File should already exist:
- `src/index.ts` — Registers all tools, commands, shortcuts, events

Verification: Ensure all tools are registered, commands wired, and context injection works.

### Step 5: Verify Skills & Prompts
Files should already exist:
- `.pi/skills/harada-coach/SKILL.md` — Coaching skill
- `.pi/prompts/checkin.md` — Morning check-in template
- `.pi/prompts/reflect.md` — Evening reflection template
- `.pi/prompts/review.md` — Weekly review template

### Step 6: Integration Test
1. Start pi with the extension: `pi -e .pi/extensions/harada-method/src/index.ts`
2. Verify extension loads without errors
3. Test `/harada-setup` command appears
4. Test tool availability — ask the agent "What harada tools do you have?"
5. Test goal form creation — walk through setup
6. Test OW64 chart creation
7. Test habit tracking
8. Test journal entry
9. Test `/harada` dashboard overlay
10. Test `/ow64` grid overlay
11. Test `/habits` tracker overlay
12. Test progress snapshot

### Step 7: Polish
1. Fix any TypeScript errors found during testing
2. Ensure theme invalidation works correctly
3. Test edge cases: empty data, first run, missing fields
4. Verify widget and status updates after each tool call
5. Test coaching nudges on session start

### Step 8: Git Commit
```bash
git add .pi/extensions/harada-method/ .pi/skills/ .pi/prompts/ .pi/harada-method-plan.md
git commit -m "feat: add Harada Method goal achievement extension

- Long-term Goal Form for north star definition
- Open Window 64 chart with 8 goals × 8 actions
- Daily habit tracking with streaks and completion rates
- Daily journal with mood/energy tracking
- Visual dashboard overlay (Ctrl+H or /harada)
- OW64 mandala grid overlay (/ow64)
- Interactive habit tracker overlay (/habits)
- Coaching skill with prompt templates
- Context injection for agent awareness
- Progress analytics and insights"
```

## Resume Points

If you need to resume from a specific step, the user can say:
- "Resume from step N" to skip to that step
- "Fix step N" to re-examine and fix issues in that step
- "Test overlays" to jump to overlay testing
- "Full build" to run all steps in sequence

## Important Notes

- The extension uses `@sinclair/typebox` for schema definitions and `@mariozechner/pi-ai` for `StringEnum`
- All imports from sibling files use `.js` extensions (ESM compatibility)
- Data persists to `.pi/harada/` as JSON files
- Overlay components use `{ overlay: true }` in `ctx.ui.custom()`
- State reconstruction happens on session events (start, switch, fork, tree)
- Widget updates trigger after every harada tool call via `tool_result` event
