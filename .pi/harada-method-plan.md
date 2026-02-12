# Harada Method Integration — Implementation Plan

## Overview

A custom agentic mode for pi that implements the **Harada Method** (原田メソッド) — a structured goal-achievement system created by Takashi Harada. The agent acts as a personal Harada coach that helps you define your ultimate north star, decompose it into actionable steps via the Open Window 64 chart, track daily habits, and provide ongoing accountability through journaling and visual progress dashboards.

**Reference:** [Using the Harada Method to Develop People](https://www.slideshare.net/slideshow/using-the-harada-method-to-develop-people/139352189)

---

## The Harada Method — Core Components

### 1. Long-term Goal Form (目標達成シート)
- **North Star Goal**: One clear, measurable ultimate objective
- **Purpose/Why**: Deep motivation behind the goal
- **Deadline**: Target completion date
- **Current State**: Honest assessment of where you are now
- **Gap Analysis**: Difference between current state and goal
- **Expected Obstacles**: What could derail progress
- **Support Needed**: People, resources, tools required
- **Daily Affirmation**: A motivational statement to reinforce commitment

### 2. Open Window 64 (OW64 Mandala Chart)
- **Center**: The north star goal
- **8 Supporting Goals**: Key pillars that must be achieved to reach the north star
- **64 Action Items**: Each supporting goal decomposes into 8 concrete, actionable tasks
- This creates a visual mandala where every action traces back to the ultimate goal

### 3. Daily Routine Check Sheet
- Select habits from the 64 actions that should be done daily/weekly
- Binary tracking: done ✓ or not done ✗ each day
- Calculate streaks, completion rates, and consistency scores
- 30-day rolling view

### 4. Daily Journal / Reflection
- What went well today
- What didn't go as planned
- Key learnings
- Tomorrow's focus areas
- Mood/energy rating

---

## Architecture

### File Structure
```
.pi/
├── extensions/
│   └── harada-method/
│       ├── package.json          # Extension manifest + deps
│       ├── src/
│       │   ├── index.ts          # Extension entry — registers all tools, commands, events
│       │   ├── tools/
│       │   │   ├── goal-form.ts      # Tool: harada_goal_form — manage long-term goal form
│       │   │   ├── ow64.ts           # Tool: harada_ow64 — manage Open Window 64 chart
│       │   │   ├── habits.ts         # Tool: harada_habits — daily habit tracking
│       │   │   ├── journal.ts        # Tool: harada_journal — daily reflection entries
│       │   │   └── progress.ts       # Tool: harada_progress — query progress & analytics
│       │   ├── ui/
│       │   │   ├── dashboard.ts      # Overlay: main Harada dashboard
│       │   │   ├── ow64-grid.ts      # Overlay: OW64 mandala visualization
│       │   │   ├── habit-tracker.ts  # Overlay: daily habit check sheet
│       │   │   ├── streak-chart.ts   # Component: streak/progress bars
│       │   │   └── theme.ts          # Dashboard color theming helpers
│       │   ├── data/
│       │   │   ├── store.ts          # Data persistence layer (JSON files)
│       │   │   ├── types.ts          # TypeScript interfaces for all Harada data
│       │   │   └── analytics.ts      # Progress calculations, streaks, scoring
│       │   └── coaching/
│       │       ├── prompts.ts        # Dynamic coaching prompts based on state
│       │       └── nudges.ts         # Intelligent nudge system (reminders, encouragement)
│       └── node_modules/             # After npm install
├── skills/
│   └── harada-coach/
│       └── SKILL.md                  # Coaching skill for guided Harada sessions
├── prompts/
│   ├── checkin.md                    # /checkin — daily check-in template
│   ├── reflect.md                    # /reflect — evening reflection template
│   └── review.md                     # /review — weekly review template
└── harada/                           # Data directory
    ├── goal-form.json                # Long-term goal form data
    ├── ow64.json                     # Open Window 64 chart data
    ├── habits.json                   # Habit definitions
    ├── habit-log.json                # Daily habit completion log
    └── journal/                      # Daily journal entries
        └── YYYY-MM-DD.json
```

---

## Phase 1: Data Layer & Types (`src/data/`)

### types.ts — Core Data Models

```typescript
// Long-term Goal Form
interface GoalForm {
  northStar: string;              // The ultimate goal
  purpose: string;                // Why this matters
  deadline: string;               // ISO date
  currentState: string;           // Where you are now
  gapAnalysis: string;            // What's missing
  obstacles: string[];            // Expected challenges
  supportNeeded: string[];        // Resources/people needed
  affirmation: string;            // Daily motivational statement
  createdAt: string;              // ISO date
  updatedAt: string;
}

// Open Window 64 Chart
interface OW64Chart {
  northStar: string;              // Center cell (mirrors GoalForm)
  supportingGoals: SupportingGoal[];  // 8 goals
}

interface SupportingGoal {
  id: number;                     // 1-8
  title: string;                  // The supporting goal
  actions: ActionItem[];          // 8 actions per goal
}

interface ActionItem {
  id: string;                     // "1-1" through "8-8"
  goalId: number;                 // Parent supporting goal
  text: string;                   // The action description
  completed: boolean;             // Whether fully achieved
  isHabit: boolean;               // Promote to daily habit?
  completedAt?: string;           // ISO date when completed
}

// Habit Tracking
interface Habit {
  id: string;                     // Unique ID
  actionId: string;               // Links to OW64 action
  name: string;                   // Short name for display
  frequency: "daily" | "weekday" | "weekly";
  active: boolean;
}

interface HabitLog {
  [date: string]: {               // "YYYY-MM-DD"
    [habitId: string]: boolean;   // completed or not
  };
}

// Journal
interface JournalEntry {
  date: string;                   // "YYYY-MM-DD"
  wentWell: string[];
  didntGoWell: string[];
  learnings: string[];
  tomorrowFocus: string[];
  mood: 1 | 2 | 3 | 4 | 5;      // 1=terrible, 5=excellent
  energy: 1 | 2 | 3 | 4 | 5;
  notes?: string;
}

// Analytics
interface ProgressSnapshot {
  ow64Completion: number;         // % of 64 actions completed
  goalCompletion: number[];       // % per supporting goal
  habitStreak: number;            // Current consecutive days
  habitCompletionRate: number;    // Last 30 days %
  journalStreak: number;          // Consecutive journal days
  daysToDeadline: number;
  todayHabitsCompleted: number;
  todayHabitsTotal: number;
}
```

### store.ts — Persistence Layer
- Read/write JSON files from `.pi/harada/`
- Atomic writes (write to temp, rename)
- Auto-create directories
- Merge/migration support for schema changes

### analytics.ts — Progress Engine
- Calculate completion percentages per goal and overall
- Compute habit streaks (current, longest)
- Rolling 30-day completion rates
- Mood/energy trends from journal
- Days remaining to deadline with projected pace
- Generate coaching insights (falling behind, on track, ahead)

---

## Phase 2: Custom Tools (`src/tools/`)

### Tool: `harada_goal_form`
**Purpose:** Create and manage the long-term goal form
**Actions:**
- `setup` — Interactive guided setup (asks questions one by one)
- `view` — Display the current goal form
- `update` — Modify specific fields
- `export` — Export to markdown

### Tool: `harada_ow64`
**Purpose:** Manage the Open Window 64 chart
**Actions:**
- `setup` — Guided creation of supporting goals and actions
- `view` — Display the full OW64 chart
- `set_goal` — Set/update a supporting goal (1-8)
- `set_action` — Set/update an action item
- `complete` — Mark an action as completed
- `promote_habit` — Promote an action to a daily habit
- `export` — Export chart to markdown

### Tool: `harada_habits`
**Purpose:** Daily habit tracking
**Actions:**
- `list` — Show today's habits with status
- `check` — Mark a habit as done for today
- `uncheck` — Undo a habit check
- `add` — Add a custom habit (not from OW64)
- `remove` — Deactivate a habit
- `history` — Show habit completion history (last N days)

### Tool: `harada_journal`
**Purpose:** Daily reflection journaling
**Actions:**
- `write` — Create/update today's journal entry
- `read` — Read a specific day's entry
- `list` — List recent entries with mood summaries
- `streak` — Show current journaling streak

### Tool: `harada_progress`
**Purpose:** Query progress analytics
**Actions:**
- `snapshot` — Full progress overview
- `trends` — Mood/energy/completion trends
- `insights` — AI-generated coaching insights
- `report` — Weekly/monthly summary report

---

## Phase 3: UI Components (`src/ui/`)

### Dashboard Overlay (`/harada` command + Ctrl+H shortcut)

A centered overlay showing the full Harada dashboard:

```
╭─────────────────── 🎯 HARADA DASHBOARD ───────────────────╮
│                                                             │
│  ⭐ NORTH STAR: "Become a senior ML engineer by Dec 2026"  │
│  📅 187 days remaining  |  🔥 Streak: 23 days              │
│                                                             │
│  ┌─── OW64 Progress ──────────────────────────────────┐    │
│  │  1. ML Fundamentals    ████████░░  75%  [6/8]      │    │
│  │  2. Portfolio Projects  ██████░░░░  62%  [5/8]      │    │
│  │  3. Networking          ████░░░░░░  50%  [4/8]      │    │
│  │  4. Interview Prep      ██░░░░░░░░  25%  [2/8]      │    │
│  │  5. Health & Energy     ██████░░░░  62%  [5/8]      │    │
│  │  6. Knowledge Sharing   ████░░░░░░  50%  [4/8]      │    │
│  │  7. Certifications      ██████░░░░  62%  [5/8]      │    │
│  │  8. Financial Prep      ████░░░░░░  37%  [3/8]      │    │
│  └────────────────────────────────────────────────────┘    │
│  Overall: ██████░░░░ 53%  [34/64 actions]                   │
│                                                             │
│  ┌─── Today's Habits ─────────────────────────────────┐    │
│  │  ✅ Study ML paper (30 min)                         │    │
│  │  ✅ Exercise                                        │    │
│  │  ☐  Practice coding problems                        │    │
│  │  ☐  Journal reflection                              │    │
│  │  ☐  Network (1 connection)                          │    │
│  │                                    3/5 done (60%)   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  📊 30-Day Habit Rate: 78%  |  📓 Journal: 18/30 days      │
│  😊 Avg Mood: 3.8/5  |  ⚡ Avg Energy: 3.5/5              │
│                                                             │
│  ↑↓ navigate sections • h check habit • enter details      │
│  j journal • r refresh • q close                            │
╰─────────────────────────────────────────────────────────────╯
```

### OW64 Mandala Grid (`/ow64` command)

A 9×9 grid overlay showing the full Open Window 64 chart in mandala form:

```
╭──────────────── 📊 OPEN WINDOW 64 ────────────────╮
│                                                     │
│  ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐ │
│  │ 1-1 │ 1-2 │ 1-3 │ 2-1 │ 2-2 │ 2-3 │ 3-1 │ 3-2 │ │
│  │     │     │     │     │     │     │     │     │ │
│  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤ │
│  │ 1-4 │ G1  │ 1-5 │ 2-4 │ G2  │ 2-5 │ 3-4 │ G3  │ │
│  │     │ ██  │     │     │ ██  │     │     │ ██  │ │
│  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤ │
│  │ 1-6 │ 1-7 │ 1-8 │ 2-6 │ 2-7 │ 2-8 │ 3-6 │ 3-7 │ │
│  │     │     │     │     │     │     │     │     │ │
│  ├═════╪═════╪═════╪═════╪═════╪═════╪═════╪═════┤ │
│  │ 4-1 │ 4-2 │ 4-3 │ G1  │ G2  │ G3  │ 5-1 │ 5-2 │ │
│  │     │     │     │     │     │     │     │     │ │
│  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤ │
│  │ 4-4 │ G4  │ 4-5 │ G8  │ ⭐  │ G5  │ 5-4 │ G5  │ │
│  │     │ ██  │     │     │GOAL │     │     │ ██  │ │
│  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤ │
│  │ ...                                         ... │ │
│  └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘ │
│                                                     │
│  🟢 completed  🟡 in progress  ⬜ not started       │
│  ↑↓←→ navigate • enter view details • q close       │
╰─────────────────────────────────────────────────────╯
```

### Habit Tracker Overlay (`/habits` command)

Weekly view of habit completion:

```
╭──────────── 📋 HABIT TRACKER ────────────╮
│                                           │
│  Week of Feb 9 - Feb 15, 2026             │
│                   M  T  W  T  F  S  S     │
│  Study ML paper   ✅ ✅ ✅ ✅ ☐  -  -     │
│  Exercise          ✅ ☐  ✅ ✅ ☐  -  -     │
│  Coding practice   ✅ ✅ ☐  ✅ ☐  -  -     │
│  Journal           ✅ ✅ ✅ ☐  ☐  -  -     │
│  Network           ☐  ✅ ☐  ✅ ☐  -  -     │
│  ──────────────────────────────────────── │
│  Daily Rate        80 80 60 80  0         │
│                                           │
│  🔥 Current Streak: 4 days               │
│  📊 30-Day Rate: 72%                      │
│  🏆 Best Streak: 15 days                  │
│                                           │
│  h check today • ←→ week • q close        │
╰───────────────────────────────────────────╯
```

### Persistent Widget (always visible above editor)

A compact 1-2 line widget showing daily status:

```
🎯 Day 47/187 | ✅ 3/5 habits | 🔥 23-day streak | 53% OW64
```

### Status Line (footer)

```
📋 harada: 3/5 habits ✅
```

---

## Phase 4: Commands & Shortcuts

| Command | Shortcut | Description |
|---------|----------|-------------|
| `/harada` | Ctrl+H | Open main dashboard overlay |
| `/ow64` | — | Open OW64 mandala grid overlay |
| `/habits` | — | Open habit tracker overlay |
| `/checkin` | — | Morning check-in (prompt template) |
| `/reflect` | — | Evening reflection (prompt template) |
| `/review` | — | Weekly review (prompt template) |
| `/harada-setup` | — | Guided first-time setup wizard |
| `/harada-export` | — | Export all data to markdown report |

---

## Phase 5: Skill — Harada Coach (`harada-coach/SKILL.md`)

A coaching skill the agent can load that provides:
- Guided goal decomposition methodology
- Socratic questioning to refine goals
- Weekly review facilitation
- Obstacle identification and mitigation strategies
- Encouragement and accountability patterns
- Knowledge of the full Harada Method framework

---

## Phase 6: Intelligent Coaching (`src/coaching/`)

### Nudge System
- **Session start**: Show affirmation + today's focus
- **Idle detection**: If habits incomplete late in day, gentle reminder
- **Milestone celebrations**: When completing a supporting goal or hitting streak milestones
- **Course corrections**: When completion rate drops below threshold

### Dynamic Context Injection
- `before_agent_start`: Inject current Harada state so the agent always knows:
  - Today's habit status
  - Current streak
  - Progress overview
  - Relevant coaching context

---

## Phase 7: Prompt Templates

### `/checkin` — Morning Check-in
```markdown
Good morning! Let's start the day with intention.

My affirmation: {affirmation}
Today is day {dayNumber} of {totalDays} toward my north star.

What are my top 3 priorities today that move me toward my goals?
Which habits am I committing to completing today?
Any obstacles I should prepare for?
```

### `/reflect` — Evening Reflection
```markdown
Time for today's reflection.

Habits completed: {completed}/{total}
Guide me through my journal entry:
- What went well today?
- What didn't go as planned?
- What did I learn?
- What should I focus on tomorrow?
```

### `/review` — Weekly Review
```markdown
Weekly review time. Show me my progress this week:
- Habit completion rates by day
- OW64 actions completed this week
- Journal consistency
- Mood and energy trends
Help me identify patterns and adjust my approach for next week.
```

---

## Implementation Order (Macro Steps)

### Step 1: Foundation (Data Layer)
1. Create `types.ts` with all interfaces
2. Create `store.ts` with JSON persistence
3. Create `analytics.ts` with progress calculations
4. Write unit-testable pure functions

### Step 2: Extension Skeleton
1. Create `package.json` with pi manifest
2. Create `index.ts` entry point
3. Register session events for state management
4. Register Ctrl+H shortcut

### Step 3: Goal Form Tool
1. Implement `harada_goal_form` tool
2. Guided interactive setup via `ctx.ui` dialogs
3. Render call/result customization
4. Test: set up a goal form via conversation

### Step 4: OW64 Tool
1. Implement `harada_ow64` tool
2. Agent-guided decomposition of north star → 8 goals → 64 actions
3. Action completion tracking
4. Habit promotion flow
5. Test: build out full OW64 from conversation

### Step 5: Habit Tracking Tool
1. Implement `harada_habits` tool
2. Daily check/uncheck with date handling
3. Streak calculation and history
4. Test: track habits for several simulated days

### Step 6: Journal Tool
1. Implement `harada_journal` tool
2. Structured entry creation
3. History browsing
4. Test: write journal entries

### Step 7: Progress Tool
1. Implement `harada_progress` tool
2. Aggregate analytics across all data
3. Trend calculations
4. Test: verify analytics accuracy

### Step 8: Dashboard Overlay
1. Build `dashboard.ts` TUI component
2. Implement progress bars with ANSI styling
3. Habit checklist with keyboard interaction
4. Wire up `/harada` command and Ctrl+H
5. Test: open dashboard, verify data display

### Step 9: OW64 Grid Overlay
1. Build `ow64-grid.ts` TUI component
2. 9×9 mandala grid rendering
3. Color-coded completion status
4. Navigation and detail drill-down
5. Wire up `/ow64` command

### Step 10: Habit Tracker Overlay
1. Build `habit-tracker.ts` TUI component
2. Weekly calendar view
3. Inline habit checking
4. Streak and rate display
5. Wire up `/habits` command

### Step 11: Persistent Widget & Status
1. Implement `setWidget` for daily progress summary
2. Implement `setStatus` for footer indicator
3. Update on session events and tool calls

### Step 12: Coaching & Prompts
1. Create `SKILL.md` for harada-coach
2. Create prompt templates (checkin, reflect, review)
3. Implement nudge system in session_start
4. Implement context injection in before_agent_start

### Step 13: Polish & Testing
1. Theme-aware rendering (invalidation)
2. Edge cases (empty data, first run, date boundaries)
3. Data migration support
4. Export functionality
5. README documentation

---

## Data Flow

```
User ←→ Pi Agent ←→ Harada Extension
                        │
                        ├── Tools (LLM callable)
                        │     ├── Read/write .pi/harada/*.json
                        │     └── Return structured results
                        │
                        ├── UI (User facing)
                        │     ├── Dashboard overlay
                        │     ├── OW64 grid overlay
                        │     ├── Habit tracker overlay
                        │     ├── Persistent widget
                        │     └── Status line
                        │
                        ├── Events (Automatic)
                        │     ├── session_start → load data, show nudge
                        │     ├── before_agent_start → inject context
                        │     ├── tool_result → update widget
                        │     └── session_shutdown → save state
                        │
                        └── Coaching (Contextual)
                              ├── Dynamic prompts based on state
                              ├── Milestone celebrations
                              └── Course correction nudges
```

---

## Success Criteria

- [ ] Can set up a complete Harada goal form through conversation
- [ ] Can decompose north star into 8 goals × 8 actions via guided dialog
- [ ] Can track daily habits with persistent streaks across sessions
- [ ] Can write structured daily journal entries
- [ ] Dashboard overlay shows real-time progress visually
- [ ] OW64 mandala grid renders the full 64-action chart
- [ ] Habit tracker shows weekly calendar with completion marks
- [ ] Widget always shows current daily progress at a glance
- [ ] Agent automatically knows your Harada context in every conversation
- [ ] Coaching nudges appear at session start when relevant
- [ ] All data persists across pi sessions via JSON files
- [ ] Weekly review provides actionable insights
