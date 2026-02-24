"""Harada Method tool functions for voice agent.

Reads/writes .pi/harada/*.json — same data format as the pi extension.
Tools are voice-friendly: fuzzy matching, natural language output.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Project directory (where .pi/harada/ lives)
PROJECT_DIR = Path(__file__).parent
HARADA_DIR = PROJECT_DIR / ".pi" / "harada"


# ── JSON Helpers ─────────────────────────────────────────

def _ensure_dir():
    """Ensure harada data directory exists."""
    HARADA_DIR.mkdir(parents=True, exist_ok=True)
    (HARADA_DIR / "journal").mkdir(exist_ok=True)


def _read_json(filename):
    """Read a JSON file from harada dir. Returns None if missing."""
    path = HARADA_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _write_json(filename, data):
    """Write JSON atomically to harada dir."""
    _ensure_dir()
    path = HARADA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.rename(tmp, str(path))


def _today():
    """Today as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def _days_ago(n):
    """Date N days ago as YYYY-MM-DD."""
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


def _fuzzy_match(query, candidates):
    """Find best matching candidate by substring (case-insensitive).
    Returns (matched_item, score) or (None, 0)."""
    query_lower = query.lower().strip()
    if not query_lower:
        return None, 0
    best = None
    best_score = 0
    for item in candidates:
        name_lower = item["name"].lower()
        if query_lower == name_lower:
            return item, 100  # Exact match
        # Check if query words all appear in name
        query_words = query_lower.split()
        name_words = name_lower.split()
        all_words_match = all(
            any(qw in nw for nw in name_words) for qw in query_words
        )
        if query_lower in name_lower:
            # Substring match — score based on coverage, minimum 40 for any match
            score = max(40, len(query_lower) / len(name_lower) * 90)
            if score > best_score:
                best = item
                best_score = score
        elif all_words_match:
            # All query words found in name words
            score = 60
            if score > best_score:
                best = item
                best_score = score
        elif name_lower in query_lower:
            score = max(40, len(name_lower) / len(query_lower) * 80)
            if score > best_score:
                best = item
                best_score = score
    return best, best_score


# ── Tool Functions ───────────────────────────────────────

def list_habits(**kwargs):
    """List today's habits with completion status."""
    habits = _read_json("habits.json") or []
    habit_log = _read_json("habit-log.json") or {}
    today = _today()
    today_log = habit_log.get(today, {})

    active = [h for h in habits if h.get("active", True)]
    if not active:
        return "You don't have any habits set up yet. Would you like to create some?"

    lines = []
    completed = 0
    for h in active:
        done = today_log.get(h["id"], False)
        if done:
            completed += 1
        mark = "done" if done else "not done"
        lines.append(f"- {h['name']}: {mark}")

    total = len(active)
    header = f"Today's habits ({completed}/{total} done):\n"
    return header + "\n".join(lines)


def check_habit(habit_name, **kwargs):
    """Mark a habit as done for today. Uses fuzzy name matching."""
    habits = _read_json("habits.json") or []
    active = [h for h in habits if h.get("active", True)]

    if not active:
        return "No habits set up yet."

    match, score = _fuzzy_match(habit_name, active)
    if not match or score < 30:
        names = ", ".join(h["name"] for h in active)
        return f"I couldn't find a habit matching '{habit_name}'. Your habits are: {names}"

    habit_log = _read_json("habit-log.json") or {}
    today = _today()
    if today not in habit_log:
        habit_log[today] = {}
    habit_log[today][match["id"]] = True
    _write_json("habit-log.json", habit_log)

    # Count today's completion
    today_log = habit_log[today]
    completed = sum(1 for h in active if today_log.get(h["id"], False))
    total = len(active)

    if completed == total:
        return f"Checked off '{match['name']}'! That's all {total} habits done for today! Amazing work!"
    else:
        return f"Checked off '{match['name']}'! That's {completed} out of {total} done today."


def uncheck_habit(habit_name, **kwargs):
    """Unmark a habit for today."""
    habits = _read_json("habits.json") or []
    active = [h for h in habits if h.get("active", True)]

    match, score = _fuzzy_match(habit_name, active)
    if not match or score < 30:
        return f"I couldn't find a habit matching '{habit_name}'."

    habit_log = _read_json("habit-log.json") or {}
    today = _today()
    if today in habit_log and match["id"] in habit_log[today]:
        habit_log[today][match["id"]] = False
        _write_json("habit-log.json", habit_log)

    return f"Unchecked '{match['name']}' for today."


def add_habit(name, frequency="daily", **kwargs):
    """Add a new daily habit."""
    import uuid
    habits = _read_json("habits.json") or []
    habit_id = f"habit-custom-{uuid.uuid4().hex[:8]}"
    habits.append({
        "id": habit_id,
        "name": name,
        "frequency": frequency,
        "active": True,
        "createdAt": datetime.now().isoformat(),
    })
    _write_json("habits.json", habits)
    return f"Added new habit: '{name}' ({frequency}). You now have {len([h for h in habits if h.get('active', True)])} active habits."


def remove_habit(habit_name, **kwargs):
    """Deactivate a habit."""
    habits = _read_json("habits.json") or []
    active = [h for h in habits if h.get("active", True)]

    match, score = _fuzzy_match(habit_name, active)
    if not match or score < 30:
        return f"I couldn't find a habit matching '{habit_name}'."

    for h in habits:
        if h["id"] == match["id"]:
            h["active"] = False
    _write_json("habits.json", habits)
    return f"Removed habit: '{match['name']}'."


def get_progress(**kwargs):
    """Get a full progress snapshot in natural language."""
    goal_form = _read_json("goal-form.json")
    if not goal_form:
        return "No Harada goal set up yet. Let's start by defining your north star goal!"

    ow64 = _read_json("ow64.json")
    habits = _read_json("habits.json") or []
    habit_log = _read_json("habit-log.json") or {}
    today = _today()
    today_log = habit_log.get(today, {})

    active_habits = [h for h in habits if h.get("active", True)]
    habits_done = sum(1 for h in active_habits if today_log.get(h["id"], False))
    habits_total = len(active_habits)

    # Streak calculation
    streak = 0
    if active_habits:
        for i in range(365):
            d = _days_ago(i)
            day_log = habit_log.get(d, {})
            all_done = all(day_log.get(h["id"], False) for h in active_habits)
            if all_done:
                streak += 1
            else:
                break

    # OW64 completion
    ow64_done = 0
    ow64_total = 0
    goal_summaries = []
    if ow64 and ow64.get("supportingGoals"):
        for g in ow64["supportingGoals"]:
            if not g.get("title"):
                continue
            actions = g.get("actions", [])
            done = sum(1 for a in actions if a.get("completed"))
            total = len([a for a in actions if a.get("text")])
            ow64_done += done
            ow64_total += total
            pct = round(done / total * 100) if total > 0 else 0
            goal_summaries.append(f"  Goal {g['id']} '{g['title']}': {done}/{total} ({pct}%)")

    # Days
    days_info = ""
    if goal_form.get("deadline"):
        try:
            deadline = datetime.fromisoformat(goal_form["deadline"])
            days_left = (deadline - datetime.now()).days
            if days_left > 0:
                days_info = f"{days_left} days remaining to deadline. "
        except ValueError:
            pass
    if goal_form.get("createdAt"):
        try:
            created = datetime.fromisoformat(goal_form["createdAt"][:10])
            days_since = (datetime.now() - created).days
            days_info += f"Day {days_since} of your journey."
        except ValueError:
            pass

    # Journal info
    journal_dir = HARADA_DIR / "journal"
    journal_count = 0
    if journal_dir.exists():
        journal_count = len([f for f in journal_dir.iterdir() if f.suffix == ".json"])

    # Build response
    parts = [
        f"North star: {goal_form['northStar']}.",
        days_info,
        f"Today's habits: {habits_done}/{habits_total} done.",
    ]
    if streak > 0:
        parts.append(f"Current streak: {streak} days.")
    if ow64_total > 0:
        ow64_pct = round(ow64_done / ow64_total * 100)
        parts.append(f"OW64 progress: {ow64_done}/{ow64_total} actions completed ({ow64_pct}%).")
    if goal_summaries:
        parts.append("By goal:\n" + "\n".join(goal_summaries))
    if journal_count > 0:
        parts.append(f"Journal entries: {journal_count} total.")
    if goal_form.get("affirmation"):
        parts.append(f"Your affirmation: {goal_form['affirmation']}")

    return "\n".join(parts)


def get_goals(**kwargs):
    """Get the north star and supporting goals."""
    goal_form = _read_json("goal-form.json")
    ow64 = _read_json("ow64.json")

    if not goal_form:
        return "No goal form set up yet. Let's define your north star!"

    parts = [
        f"North star: {goal_form['northStar']}",
        f"Purpose: {goal_form.get('purpose', 'Not set')}",
        f"Deadline: {goal_form.get('deadline', 'Not set')}",
        f"Affirmation: {goal_form.get('affirmation', 'Not set')}",
    ]

    if ow64 and ow64.get("supportingGoals"):
        parts.append("\nSupporting goals:")
        for g in ow64["supportingGoals"]:
            if g.get("title"):
                actions = g.get("actions", [])
                done = sum(1 for a in actions if a.get("completed"))
                total = len([a for a in actions if a.get("text")])
                parts.append(f"  {g['id']}. {g['title']} ({done}/{total} actions done)")

    return "\n".join(parts)


def get_affirmation(**kwargs):
    """Get the user's daily affirmation."""
    goal_form = _read_json("goal-form.json")
    if not goal_form or not goal_form.get("affirmation"):
        return "No affirmation set. Would you like to create one?"
    return goal_form["affirmation"]


def setup_goal(north_star, purpose="", deadline="", current_state="",
               gap_analysis="", obstacles=None, support_needed=None,
               affirmation="", **kwargs):
    """Create or update the long-term goal form."""
    existing = _read_json("goal-form.json")
    now = datetime.now().isoformat()

    form = {
        "northStar": north_star,
        "purpose": purpose,
        "deadline": deadline,
        "currentState": current_state,
        "gapAnalysis": gap_analysis,
        "obstacles": obstacles or [],
        "supportNeeded": support_needed or [],
        "affirmation": affirmation,
        "createdAt": existing["createdAt"] if existing else now,
        "updatedAt": now,
    }
    _write_json("goal-form.json", form)
    return f"Goal form saved! North star: '{north_star}'. " + (f"Deadline: {deadline}. " if deadline else "") + (f"Affirmation: '{affirmation}'" if affirmation else "")


def setup_supporting_goal(goal_number, title, actions=None, **kwargs):
    """Set or update a supporting goal in the OW64 chart."""
    goal_form = _read_json("goal-form.json")
    if not goal_form:
        return "Set up your north star goal first."

    ow64 = _read_json("ow64.json")
    if not ow64:
        ow64 = {
            "northStar": goal_form["northStar"],
            "supportingGoals": []
        }
        for i in range(1, 9):
            ow64["supportingGoals"].append({
                "id": i,
                "title": "",
                "actions": [
                    {"id": f"{i}-{j}", "goalId": i, "text": "", "completed": False, "isHabit": False}
                    for j in range(1, 9)
                ]
            })

    if goal_number < 1 or goal_number > 8:
        return "Goal number must be 1-8."

    goal = ow64["supportingGoals"][goal_number - 1]
    goal["title"] = title

    if actions:
        for idx, text in enumerate(actions[:8]):
            goal["actions"][idx]["text"] = text

    _write_json("ow64.json", ow64)

    action_count = len(actions) if actions else 0
    return f"Supporting goal {goal_number} set: '{title}'" + (f" with {action_count} actions." if action_count else ".")


def complete_action(goal_number, action_number, **kwargs):
    """Mark an OW64 action as completed."""
    ow64 = _read_json("ow64.json")
    if not ow64:
        return "No OW64 chart set up."

    if goal_number < 1 or goal_number > 8:
        return "Goal number must be 1-8."
    if action_number < 1 or action_number > 8:
        return "Action number must be 1-8."

    goal = ow64["supportingGoals"][goal_number - 1]
    action = goal["actions"][action_number - 1]

    if not action.get("text"):
        return f"Action {goal_number}-{action_number} has no text defined."

    action["completed"] = True
    action["completedAt"] = datetime.now().isoformat()
    _write_json("ow64.json", ow64)

    done = sum(1 for a in goal["actions"] if a.get("completed"))
    return f"Completed action {goal_number}-{action_number}: '{action['text']}'! That's {done}/8 for goal '{goal['title']}'."


def write_journal(went_well=None, didnt_go_well=None, learnings=None,
                  tomorrow_focus=None, mood=None, energy=None, notes=None, **kwargs):
    """Write today's journal entry."""
    today = _today()
    now = datetime.now().isoformat()
    existing = _read_json(f"journal/{today}.json") or {}

    # Merge: only override fields that were explicitly provided
    mood = mood if mood is not None else existing.get("mood", 3)
    energy = energy if energy is not None else existing.get("energy", 3)

    entry = {
        "date": today,
        "wentWell": went_well if went_well is not None else existing.get("wentWell", []),
        "didntGoWell": didnt_go_well if didnt_go_well is not None else existing.get("didntGoWell", []),
        "learnings": learnings if learnings is not None else existing.get("learnings", []),
        "tomorrowFocus": tomorrow_focus if tomorrow_focus is not None else existing.get("tomorrowFocus", []),
        "mood": mood,
        "energy": energy,
        "notes": notes if notes is not None else existing.get("notes", ""),
        "createdAt": existing.get("createdAt", now),
        "updatedAt": now,
    }
    _write_json(f"journal/{today}.json", entry)

    mood_emoji = {1: "rough", 2: "meh", 3: "okay", 4: "good", 5: "great"}
    energy_emoji = {1: "drained", 2: "low", 3: "moderate", 4: "high", 5: "energized"}

    return (
        f"Journal saved for {today}. "
        f"Mood: {mood_emoji.get(mood, 'okay')} ({mood}/5). "
        f"Energy: {energy_emoji.get(energy, 'moderate')} ({energy}/5). "
        f"{len(entry['wentWell'])} wins, {len(entry['didntGoWell'])} challenges, {len(entry['learnings'])} learnings noted."
    )


def read_journal(date=None, **kwargs):
    """Read a journal entry."""
    date = date or _today()
    entry = _read_json(f"journal/{date}.json")
    if not entry:
        return f"No journal entry for {date}."

    parts = [f"Journal for {date}:"]
    if entry.get("wentWell"):
        parts.append("What went well: " + "; ".join(entry["wentWell"]))
    if entry.get("didntGoWell"):
        parts.append("Challenges: " + "; ".join(entry["didntGoWell"]))
    if entry.get("learnings"):
        parts.append("Learnings: " + "; ".join(entry["learnings"]))
    if entry.get("tomorrowFocus"):
        parts.append("Tomorrow's focus: " + "; ".join(entry["tomorrowFocus"]))
    parts.append(f"Mood: {entry.get('mood', '?')}/5, Energy: {entry.get('energy', '?')}/5")
    if entry.get("notes"):
        parts.append(f"Notes: {entry['notes']}")

    return "\n".join(parts)


# ── Tool Definitions (OpenAI function calling format) ────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_habits",
            "description": "List today's habits with their completion status",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_habit",
            "description": "Mark a habit as done for today. Uses fuzzy name matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_name": {"type": "string", "description": "The name (or partial name) of the habit to check off"}
                },
                "required": ["habit_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uncheck_habit",
            "description": "Undo a habit check for today",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_name": {"type": "string", "description": "The name of the habit to uncheck"}
                },
                "required": ["habit_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_habit",
            "description": "Add a new habit to track daily",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the new habit"},
                    "frequency": {"type": "string", "enum": ["daily", "weekday", "weekly"], "description": "How often (default: daily)"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_habit",
            "description": "Remove/deactivate a habit",
            "parameters": {
                "type": "object",
                "properties": {
                    "habit_name": {"type": "string", "description": "Name of habit to remove"}
                },
                "required": ["habit_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": "Get a full progress snapshot: north star, habits, streaks, OW64 completion, journal stats",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_goals",
            "description": "Get the north star goal and all supporting goals from the OW64 chart",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_affirmation",
            "description": "Get the user's daily affirmation statement",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "setup_goal",
            "description": "Create or update the north star goal form. Call this when the user defines their main goal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "north_star": {"type": "string", "description": "The ultimate north star goal"},
                    "purpose": {"type": "string", "description": "Why this goal matters (deep motivation)"},
                    "deadline": {"type": "string", "description": "Target date YYYY-MM-DD"},
                    "current_state": {"type": "string", "description": "Where they are now"},
                    "gap_analysis": {"type": "string", "description": "Gap between current and goal state"},
                    "obstacles": {"type": "array", "items": {"type": "string"}, "description": "Expected challenges"},
                    "support_needed": {"type": "array", "items": {"type": "string"}, "description": "Resources/people needed"},
                    "affirmation": {"type": "string", "description": "Daily affirmation in present tense"}
                },
                "required": ["north_star"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "setup_supporting_goal",
            "description": "Set a supporting goal (1-8) in the OW64 chart with its actions",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_number": {"type": "integer", "description": "Goal number 1-8"},
                    "title": {"type": "string", "description": "Title of the supporting goal"},
                    "actions": {"type": "array", "items": {"type": "string"}, "description": "Up to 8 action items for this goal"}
                },
                "required": ["goal_number", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_action",
            "description": "Mark an OW64 action as completed",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_number": {"type": "integer", "description": "Supporting goal number 1-8"},
                    "action_number": {"type": "integer", "description": "Action number 1-8 within the goal"}
                },
                "required": ["goal_number", "action_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_journal",
            "description": "Write or update today's journal entry",
            "parameters": {
                "type": "object",
                "properties": {
                    "went_well": {"type": "array", "items": {"type": "string"}, "description": "Things that went well"},
                    "didnt_go_well": {"type": "array", "items": {"type": "string"}, "description": "Things that didn't go well"},
                    "learnings": {"type": "array", "items": {"type": "string"}, "description": "Key learnings"},
                    "tomorrow_focus": {"type": "array", "items": {"type": "string"}, "description": "Focus areas for tomorrow"},
                    "mood": {"type": "integer", "description": "Mood 1-5 (1=terrible, 5=excellent)"},
                    "energy": {"type": "integer", "description": "Energy 1-5 (1=drained, 5=energized)"},
                    "notes": {"type": "string", "description": "Additional notes"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_journal",
            "description": "Read a journal entry (defaults to today)",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date to read (YYYY-MM-DD), defaults to today"}
                },
                "required": []
            }
        }
    },
]

# ── Dispatcher ───────────────────────────────────────────

_TOOL_FUNCTIONS = {
    "list_habits": list_habits,
    "check_habit": check_habit,
    "uncheck_habit": uncheck_habit,
    "add_habit": add_habit,
    "remove_habit": remove_habit,
    "get_progress": get_progress,
    "get_goals": get_goals,
    "get_affirmation": get_affirmation,
    "setup_goal": setup_goal,
    "setup_supporting_goal": setup_supporting_goal,
    "complete_action": complete_action,
    "write_journal": write_journal,
    "read_journal": read_journal,
}


def execute_tool(name: str, arguments: dict) -> str:
    """Execute a harada tool by name and return result as string."""
    func = _TOOL_FUNCTIONS.get(name)
    if not func:
        return f"Unknown tool: {name}"
    try:
        return func(**arguments)
    except Exception as e:
        return f"Tool error ({name}): {e}"


def get_overlay_state(conversation_history: list[dict] | None = None) -> dict:
    """Build the overlay state dict for Hammerspoon.

    Args:
        conversation_history: List of {"role": "user"/"assistant", "text": "..."} dicts.

    Returns:
        Dict with dashboard + conversation data for the overlay JSON.
    """
    goal_form = _read_json("goal-form.json")
    ow64 = _read_json("ow64.json")
    habits = _read_json("habits.json") or []
    habit_log = _read_json("habit-log.json") or {}
    today = _today()
    today_log = habit_log.get(today, {})

    active_habits = [h for h in habits if h.get("active", True)]
    habits_completed = sum(1 for h in active_habits if today_log.get(h["id"], False))

    # Streak
    streak = 0
    if active_habits:
        for i in range(365):
            d = _days_ago(i)
            day_log = habit_log.get(d, {})
            if all(day_log.get(h["id"], False) for h in active_habits):
                streak += 1
            else:
                break

    # OW64
    ow64_done = 0
    ow64_total = 0
    goal_progress = []
    if ow64 and ow64.get("supportingGoals"):
        for g in ow64["supportingGoals"]:
            actions = g.get("actions", [])
            filled = [a for a in actions if a.get("text")]
            done = sum(1 for a in actions if a.get("completed"))
            ow64_done += done
            ow64_total += len(filled)
            if g.get("title"):
                pct = round(done / len(filled) * 100) if filled else 0
                goal_progress.append({"id": g["id"], "title": g["title"], "pct": pct})

    # Mood/energy averages (last 30 days)
    moods = []
    energies = []
    journal_dir = HARADA_DIR / "journal"
    for i in range(30):
        d = _days_ago(i)
        entry = _read_json(f"journal/{d}.json")
        if entry:
            if entry.get("mood"):
                moods.append(entry["mood"])
            if entry.get("energy"):
                energies.append(entry["energy"])

    # Days
    days_since_start = 0
    days_remaining = -1
    if goal_form:
        if goal_form.get("createdAt"):
            try:
                created = datetime.fromisoformat(goal_form["createdAt"][:10])
                days_since_start = (datetime.now() - created).days
            except ValueError:
                pass
        if goal_form.get("deadline"):
            try:
                deadline = datetime.fromisoformat(goal_form["deadline"])
                days_remaining = (deadline - datetime.now()).days
            except ValueError:
                pass

    return {
        "timestamp": datetime.now().isoformat(),
        "conversation": conversation_history or [],
        "dashboard": {
            "northStar": goal_form["northStar"] if goal_form else "",
            "affirmation": goal_form.get("affirmation", "") if goal_form else "",
            "daysSinceStart": days_since_start,
            "daysRemaining": days_remaining,
            "habits": [
                {"name": h["name"], "done": today_log.get(h["id"], False)}
                for h in active_habits
            ],
            "habitsCompleted": habits_completed,
            "habitsTotal": len(active_habits),
            "streak": streak,
            "ow64Completion": round(ow64_done / ow64_total * 100) if ow64_total > 0 else 0,
            "ow64Done": ow64_done,
            "ow64Total": ow64_total,
            "goalProgress": goal_progress,
            "avgMood": round(sum(moods) / len(moods), 1) if moods else None,
            "avgEnergy": round(sum(energies) / len(energies), 1) if energies else None,
        }
    }
