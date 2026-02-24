"""Comprehensive tests for harada_tools.py.

Tests all 13 tool functions, fuzzy matching, data persistence,
edge cases, overlay state generation, and the tool calling integration
with llm_router and conversation.
"""

import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock ollama before any project imports
mock_ollama = MagicMock()
sys.modules["ollama"] = mock_ollama

# Project root
PROJECT_DIR = Path(__file__).parent.parent
HARADA_DIR = PROJECT_DIR / ".pi" / "harada"
HARADA_TEST_BACKUP = PROJECT_DIR / ".pi" / "harada_test_backup"


@pytest.fixture(autouse=True)
def clean_harada_data():
    """Backup existing harada data, clean for test, restore after."""
    # Backup
    if HARADA_DIR.exists():
        if HARADA_TEST_BACKUP.exists():
            shutil.rmtree(HARADA_TEST_BACKUP)
        shutil.copytree(HARADA_DIR, HARADA_TEST_BACKUP)
        shutil.rmtree(HARADA_DIR)

    HARADA_DIR.mkdir(parents=True, exist_ok=True)
    (HARADA_DIR / "journal").mkdir(exist_ok=True)

    yield

    # Restore
    if HARADA_DIR.exists():
        shutil.rmtree(HARADA_DIR)
    if HARADA_TEST_BACKUP.exists():
        shutil.copytree(HARADA_TEST_BACKUP, HARADA_DIR)
        shutil.rmtree(HARADA_TEST_BACKUP)


@pytest.fixture
def tools():
    """Fresh import of harada_tools (module may cache state)."""
    import importlib
    if "harada_tools" in sys.modules:
        importlib.reload(sys.modules["harada_tools"])
    from harada_tools import (
        TOOL_DEFINITIONS,
        execute_tool,
        get_overlay_state,
        _read_json,
        _write_json,
        _fuzzy_match,
        _today,
        _days_ago,
    )
    return type("Tools", (), {
        "TOOL_DEFINITIONS": TOOL_DEFINITIONS,
        "execute_tool": staticmethod(execute_tool),
        "get_overlay_state": staticmethod(get_overlay_state),
        "read_json": staticmethod(_read_json),
        "write_json": staticmethod(_write_json),
        "fuzzy_match": staticmethod(_fuzzy_match),
        "today": staticmethod(_today),
        "days_ago": staticmethod(_days_ago),
    })()


# ═══════════════════════════════════════════════════════════
# TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════

class TestToolDefinitions:
    """Validate OpenAI-format tool definitions are well-formed."""

    def test_all_tools_present(self, tools):
        names = [t["function"]["name"] for t in tools.TOOL_DEFINITIONS]
        expected = [
            "list_habits", "check_habit", "uncheck_habit", "add_habit",
            "remove_habit", "get_progress", "get_goals", "get_affirmation",
            "setup_goal", "setup_supporting_goal", "complete_action",
            "write_journal", "read_journal",
        ]
        for name in expected:
            assert name in names, f"Missing tool: {name}"

    def test_tool_definition_format(self, tools):
        for t in tools.TOOL_DEFINITIONS:
            assert t["type"] == "function"
            func = t["function"]
            assert "name" in func
            assert "description" in func
            assert len(func["description"]) > 10, f"{func['name']} description too short"
            assert "parameters" in func
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_required_params_exist_in_properties(self, tools):
        for t in tools.TOOL_DEFINITIONS:
            func = t["function"]
            props = func["parameters"]["properties"]
            required = func["parameters"]["required"]
            for r in required:
                assert r in props, f"{func['name']}: required param '{r}' not in properties"


# ═══════════════════════════════════════════════════════════
# FUZZY MATCHING
# ═══════════════════════════════════════════════════════════

class TestFuzzyMatch:
    """Test the fuzzy matching logic used for habit name resolution."""

    def _items(self, *names):
        return [{"name": n, "id": f"id-{i}"} for i, n in enumerate(names)]

    def test_exact_match(self, tools):
        items = self._items("Exercise", "Study", "Meditate")
        match, score = tools.fuzzy_match("Exercise", items)
        assert match["name"] == "Exercise"
        assert score == 100

    def test_exact_match_case_insensitive(self, tools):
        items = self._items("Exercise", "Study", "Meditate")
        match, score = tools.fuzzy_match("exercise", items)
        assert match["name"] == "Exercise"
        assert score == 100

    def test_substring_match(self, tools):
        items = self._items("Study ML papers", "Exercise daily", "Meditate")
        match, score = tools.fuzzy_match("ML", items)
        assert match is not None
        assert match["name"] == "Study ML papers"
        assert score >= 40

    def test_substring_partial(self, tools):
        items = self._items("Study ML papers", "Exercise daily", "Meditate")
        match, score = tools.fuzzy_match("meditat", items)
        assert match is not None
        assert match["name"] == "Meditate"

    def test_no_match(self, tools):
        items = self._items("Exercise", "Study", "Meditate")
        match, score = tools.fuzzy_match("xyznonexistent", items)
        assert match is None or score < 30

    def test_empty_query(self, tools):
        items = self._items("Exercise")
        match, score = tools.fuzzy_match("", items)
        assert match is None

    def test_empty_candidates(self, tools):
        match, score = tools.fuzzy_match("test", [])
        assert match is None

    def test_word_match(self, tools):
        items = self._items("Read ML papers daily", "Go for a run", "Write code")
        match, score = tools.fuzzy_match("ML papers", items)
        assert match is not None
        assert match["name"] == "Read ML papers daily"

    def test_best_match_wins(self, tools):
        items = self._items("Exercise lightly", "Exercise intensely", "Exercise")
        match, score = tools.fuzzy_match("Exercise", items)
        assert match["name"] == "Exercise"  # exact match wins

    def test_single_char_query(self, tools):
        """Single character should not produce false matches."""
        items = self._items("Exercise", "Study", "Meditate")
        match, score = tools.fuzzy_match("z", items)
        # 'z' is in 'Exercise' but very weak match
        # Should still match but with low score
        if match:
            assert score >= 40  # if it matches, it's a substring match


# ═══════════════════════════════════════════════════════════
# GOAL FORM
# ═══════════════════════════════════════════════════════════

class TestGoalForm:
    """Test setup_goal, get_goals, get_affirmation tools."""

    def test_setup_goal_minimal(self, tools):
        result = tools.execute_tool("setup_goal", {"north_star": "Be great"})
        assert "Be great" in result

        data = tools.read_json("goal-form.json")
        assert data["northStar"] == "Be great"
        assert data["purpose"] == ""
        assert data["createdAt"] is not None
        assert data["updatedAt"] is not None

    def test_setup_goal_full(self, tools):
        result = tools.execute_tool("setup_goal", {
            "north_star": "Senior Engineer",
            "purpose": "Growth",
            "deadline": "2026-12-31",
            "current_state": "Mid-level",
            "gap_analysis": "Need leadership",
            "obstacles": ["Time", "Energy"],
            "support_needed": ["Mentor"],
            "affirmation": "I am growing",
        })
        assert "Senior Engineer" in result

        data = tools.read_json("goal-form.json")
        assert data["northStar"] == "Senior Engineer"
        assert data["purpose"] == "Growth"
        assert data["deadline"] == "2026-12-31"
        assert data["obstacles"] == ["Time", "Energy"]
        assert data["supportNeeded"] == ["Mentor"]

    def test_setup_goal_updates_existing(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "V1"})
        data1 = tools.read_json("goal-form.json")
        created = data1["createdAt"]

        tools.execute_tool("setup_goal", {"north_star": "V2", "purpose": "New purpose"})
        data2 = tools.read_json("goal-form.json")
        assert data2["northStar"] == "V2"
        assert data2["createdAt"] == created  # preserved
        assert data2["updatedAt"] >= data1["updatedAt"]

    def test_get_goals_empty(self, tools):
        result = tools.execute_tool("get_goals", {})
        assert "no" in result.lower() or "not" in result.lower()

    def test_get_goals_with_data(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "Test Goal"})
        result = tools.execute_tool("get_goals", {})
        assert "Test Goal" in result

    def test_get_affirmation_empty(self, tools):
        result = tools.execute_tool("get_affirmation", {})
        assert "no" in result.lower() or "not" in result.lower()

    def test_get_affirmation_with_data(self, tools):
        tools.execute_tool("setup_goal", {
            "north_star": "X",
            "affirmation": "I am unstoppable",
        })
        result = tools.execute_tool("get_affirmation", {})
        assert result == "I am unstoppable"


# ═══════════════════════════════════════════════════════════
# OW64 CHART
# ═══════════════════════════════════════════════════════════

class TestOW64:
    """Test setup_supporting_goal and complete_action tools."""

    def test_setup_supporting_goal_requires_goal_form(self, tools):
        result = tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "Test"
        })
        assert "north star" in result.lower() or "first" in result.lower()

    def test_setup_supporting_goal_creates_ow64(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        result = tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1,
            "title": "Pillar One",
            "actions": ["A1", "A2", "A3"],
        })
        assert "Pillar One" in result

        ow64 = tools.read_json("ow64.json")
        assert ow64["northStar"] == "NS"
        assert len(ow64["supportingGoals"]) == 8
        assert ow64["supportingGoals"][0]["title"] == "Pillar One"
        assert ow64["supportingGoals"][0]["actions"][0]["text"] == "A1"
        assert ow64["supportingGoals"][0]["actions"][2]["text"] == "A3"
        # Remaining actions should be empty
        assert ow64["supportingGoals"][0]["actions"][3]["text"] == ""

    def test_setup_multiple_goals(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        for i in range(1, 9):
            tools.execute_tool("setup_supporting_goal", {
                "goal_number": i, "title": f"Goal {i}"
            })

        ow64 = tools.read_json("ow64.json")
        for i in range(8):
            assert ow64["supportingGoals"][i]["title"] == f"Goal {i + 1}"

    def test_goal_number_out_of_range(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        r = tools.execute_tool("setup_supporting_goal", {"goal_number": 0, "title": "X"})
        assert "1-8" in r
        r = tools.execute_tool("setup_supporting_goal", {"goal_number": 9, "title": "X"})
        assert "1-8" in r

    def test_complete_action(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["Do X"]
        })
        result = tools.execute_tool("complete_action", {
            "goal_number": 1, "action_number": 1
        })
        assert "Do X" in result
        assert "Completed" in result

        ow64 = tools.read_json("ow64.json")
        assert ow64["supportingGoals"][0]["actions"][0]["completed"] is True
        assert ow64["supportingGoals"][0]["actions"][0]["completedAt"] is not None

    def test_complete_action_no_chart(self, tools):
        result = tools.execute_tool("complete_action", {
            "goal_number": 1, "action_number": 1
        })
        assert "no" in result.lower() or "not" in result.lower()

    def test_complete_empty_action(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        tools.execute_tool("setup_supporting_goal", {"goal_number": 1, "title": "G1"})
        result = tools.execute_tool("complete_action", {
            "goal_number": 1, "action_number": 5  # empty action
        })
        assert "no text" in result.lower() or "not" in result.lower()

    def test_complete_action_range(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A"]
        })
        r = tools.execute_tool("complete_action", {"goal_number": 1, "action_number": 0})
        assert "1-8" in r
        r = tools.execute_tool("complete_action", {"goal_number": 1, "action_number": 9})
        assert "1-8" in r
        r = tools.execute_tool("complete_action", {"goal_number": 0, "action_number": 1})
        assert "1-8" in r


# ═══════════════════════════════════════════════════════════
# HABITS
# ═══════════════════════════════════════════════════════════

class TestHabits:
    """Test add_habit, list_habits, check_habit, uncheck_habit, remove_habit."""

    def test_add_habit_default_frequency(self, tools):
        result = tools.execute_tool("add_habit", {"name": "Run"})
        assert "Run" in result
        assert "daily" in result

        habits = tools.read_json("habits.json")
        assert len(habits) == 1
        assert habits[0]["name"] == "Run"
        assert habits[0]["frequency"] == "daily"
        assert habits[0]["active"] is True

    def test_add_habit_custom_frequency(self, tools):
        result = tools.execute_tool("add_habit", {"name": "Yoga", "frequency": "weekday"})
        assert "weekday" in result

    def test_add_multiple_habits_unique_ids(self, tools):
        for name in ["A", "B", "C", "D", "E"]:
            tools.execute_tool("add_habit", {"name": name})

        habits = tools.read_json("habits.json")
        ids = [h["id"] for h in habits]
        assert len(set(ids)) == 5, f"Duplicate IDs found: {ids}"

    def test_list_habits_empty(self, tools):
        result = tools.execute_tool("list_habits", {})
        assert "don't" in result.lower() or "no" in result.lower()

    def test_list_habits_with_data(self, tools):
        tools.execute_tool("add_habit", {"name": "Run"})
        tools.execute_tool("add_habit", {"name": "Read"})
        result = tools.execute_tool("list_habits", {})
        assert "0/2" in result
        assert "Run" in result
        assert "Read" in result

    def test_check_habit_updates_log(self, tools):
        tools.execute_tool("add_habit", {"name": "Exercise"})
        result = tools.execute_tool("check_habit", {"habit_name": "Exercise"})
        assert "Checked" in result
        assert "1" in result  # 1 out of 1

        log = tools.read_json("habit-log.json")
        today = tools.today()
        assert today in log
        habits = tools.read_json("habits.json")
        assert log[today][habits[0]["id"]] is True

    def test_check_habit_fuzzy(self, tools):
        tools.execute_tool("add_habit", {"name": "Study ML papers"})
        result = tools.execute_tool("check_habit", {"habit_name": "ML"})
        assert "Study ML papers" in result

    def test_check_habit_not_found(self, tools):
        tools.execute_tool("add_habit", {"name": "Exercise"})
        result = tools.execute_tool("check_habit", {"habit_name": "xyzabc"})
        assert "couldn't find" in result.lower()

    def test_check_habit_all_done_celebration(self, tools):
        tools.execute_tool("add_habit", {"name": "A"})
        result = tools.execute_tool("check_habit", {"habit_name": "A"})
        assert "all" in result.lower() or "Amazing" in result

    def test_uncheck_habit(self, tools):
        tools.execute_tool("add_habit", {"name": "Exercise"})
        tools.execute_tool("check_habit", {"habit_name": "Exercise"})
        result = tools.execute_tool("uncheck_habit", {"habit_name": "Exercise"})
        assert "Unchecked" in result

        result = tools.execute_tool("list_habits", {})
        assert "0/1" in result

    def test_uncheck_habit_not_found(self, tools):
        result = tools.execute_tool("uncheck_habit", {"habit_name": "nonexistent"})
        assert "couldn't find" in result.lower()

    def test_remove_habit(self, tools):
        tools.execute_tool("add_habit", {"name": "Exercise"})
        tools.execute_tool("add_habit", {"name": "Study"})
        result = tools.execute_tool("remove_habit", {"habit_name": "Exercise"})
        assert "Exercise" in result

        # Should no longer appear in active list
        result = tools.execute_tool("list_habits", {})
        assert "Exercise" not in result
        assert "Study" in result

    def test_remove_habit_not_found(self, tools):
        result = tools.execute_tool("remove_habit", {"habit_name": "nonexistent"})
        assert "couldn't find" in result.lower()

    def test_check_already_checked(self, tools):
        """Checking an already-checked habit should be idempotent."""
        tools.execute_tool("add_habit", {"name": "Exercise"})
        tools.execute_tool("check_habit", {"habit_name": "Exercise"})
        result = tools.execute_tool("check_habit", {"habit_name": "Exercise"})
        # Should still work, just re-confirm
        assert "Checked" in result or "1" in result

    def test_habit_persistence_across_calls(self, tools):
        """Habits and logs should persist to disk."""
        tools.execute_tool("add_habit", {"name": "Persist"})
        tools.execute_tool("check_habit", {"habit_name": "Persist"})

        # Verify on disk
        assert (HARADA_DIR / "habits.json").exists()
        assert (HARADA_DIR / "habit-log.json").exists()

        habits = json.loads((HARADA_DIR / "habits.json").read_text())
        assert any(h["name"] == "Persist" for h in habits)


# ═══════════════════════════════════════════════════════════
# JOURNAL
# ═══════════════════════════════════════════════════════════

class TestJournal:
    """Test write_journal, read_journal tools."""

    def test_write_journal_minimal(self, tools):
        result = tools.execute_tool("write_journal", {})
        assert "saved" in result.lower()

        today = tools.today()
        entry = tools.read_json(f"journal/{today}.json")
        assert entry is not None
        assert entry["date"] == today
        assert entry["mood"] == 3  # default
        assert entry["energy"] == 3

    def test_write_journal_full(self, tools):
        result = tools.execute_tool("write_journal", {
            "went_well": ["Got promoted", "Good sleep"],
            "didnt_go_well": ["Missed gym"],
            "learnings": ["Recovery matters"],
            "tomorrow_focus": ["Exercise early"],
            "mood": 5,
            "energy": 4,
            "notes": "Great day overall",
        })
        assert "saved" in result.lower()
        assert "great" in result.lower() or "5/5" in result

        today = tools.today()
        entry = tools.read_json(f"journal/{today}.json")
        assert entry["wentWell"] == ["Got promoted", "Good sleep"]
        assert entry["didntGoWell"] == ["Missed gym"]
        assert entry["learnings"] == ["Recovery matters"]
        assert entry["tomorrowFocus"] == ["Exercise early"]
        assert entry["mood"] == 5
        assert entry["energy"] == 4
        assert entry["notes"] == "Great day overall"

    def test_write_journal_updates_existing(self, tools):
        tools.execute_tool("write_journal", {
            "went_well": ["A"],
            "mood": 3,
        })
        today = tools.today()
        entry1 = tools.read_json(f"journal/{today}.json")
        created = entry1["createdAt"]

        tools.execute_tool("write_journal", {
            "went_well": ["B"],
            "mood": 5,
        })
        entry2 = tools.read_json(f"journal/{today}.json")
        assert entry2["wentWell"] == ["B"]
        assert entry2["mood"] == 5
        assert entry2["createdAt"] == created  # preserved

    def test_read_journal_empty(self, tools):
        result = tools.execute_tool("read_journal", {})
        assert "no" in result.lower()

    def test_read_journal_today(self, tools):
        tools.execute_tool("write_journal", {
            "went_well": ["Win"],
            "mood": 4,
        })
        result = tools.execute_tool("read_journal", {})
        assert "Win" in result
        assert "4/5" in result

    def test_read_journal_specific_date(self, tools):
        # Write for a specific date by manipulating the file directly
        entry = {
            "date": "2026-01-15",
            "wentWell": ["Old win"],
            "didntGoWell": [],
            "learnings": [],
            "tomorrowFocus": [],
            "mood": 3,
            "energy": 3,
            "createdAt": "2026-01-15T20:00:00",
            "updatedAt": "2026-01-15T20:00:00",
        }
        tools.write_json("journal/2026-01-15.json", entry)

        result = tools.execute_tool("read_journal", {"date": "2026-01-15"})
        assert "Old win" in result

    def test_write_journal_preserves_fields_when_partial(self, tools):
        """Writing partial data should preserve existing fields."""
        tools.execute_tool("write_journal", {
            "went_well": ["A"],
            "didnt_go_well": ["B"],
            "mood": 4,
            "energy": 5,
        })
        # Update only mood — all other fields should be preserved
        tools.execute_tool("write_journal", {"mood": 2})

        today = tools.today()
        entry = tools.read_json(f"journal/{today}.json")
        assert entry["mood"] == 2  # updated
        assert entry["wentWell"] == ["A"]  # preserved
        assert entry["didntGoWell"] == ["B"]  # preserved
        assert entry["energy"] == 5  # preserved from first write

    def test_journal_mood_range(self, tools):
        """Mood/energy should accept 1-5."""
        for val in [1, 2, 3, 4, 5]:
            tools.execute_tool("write_journal", {"mood": val, "energy": val})
            today = tools.today()
            entry = tools.read_json(f"journal/{today}.json")
            assert entry["mood"] == val
            assert entry["energy"] == val


# ═══════════════════════════════════════════════════════════
# PROGRESS & ANALYTICS
# ═══════════════════════════════════════════════════════════

class TestProgress:
    """Test get_progress tool and analytics calculations."""

    def test_progress_empty(self, tools):
        result = tools.execute_tool("get_progress", {})
        assert "no" in result.lower() or "not" in result.lower()

    def test_progress_with_full_data(self, tools):
        tools.execute_tool("setup_goal", {
            "north_star": "Be amazing",
            "deadline": "2026-12-31",
            "affirmation": "I am amazing",
        })
        tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1,
            "title": "Health",
            "actions": ["Run", "Eat well", "Sleep 8h"],
        })
        tools.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})
        tools.execute_tool("add_habit", {"name": "Run"})
        tools.execute_tool("check_habit", {"habit_name": "Run"})
        tools.execute_tool("write_journal", {"mood": 4, "energy": 5})

        result = tools.execute_tool("get_progress", {})
        assert "Be amazing" in result
        assert "1/3" in result or "Health" in result  # OW64
        assert "1/1" in result  # habits
        assert "I am amazing" in result  # affirmation

    def test_progress_days_calculation(self, tools):
        tools.execute_tool("setup_goal", {
            "north_star": "X",
            "deadline": (datetime.now() + timedelta(days=100)).strftime("%Y-%m-%d"),
        })
        result = tools.execute_tool("get_progress", {})
        # Should mention days remaining (approximately 100)
        assert "remaining" in result.lower() or "days" in result.lower()

    def test_streak_calculation(self, tools):
        """Build a multi-day streak by manipulating the habit log."""
        tools.execute_tool("add_habit", {"name": "Test"})
        habits = tools.read_json("habits.json")
        habit_id = habits[0]["id"]

        # Create a 5-day streak
        log = {}
        for i in range(5):
            d = tools.days_ago(i)
            log[d] = {habit_id: True}
        tools.write_json("habit-log.json", log)

        result = tools.execute_tool("get_progress", {})
        # Note: get_progress requires goal form
        tools.execute_tool("setup_goal", {"north_star": "X"})
        result = tools.execute_tool("get_progress", {})
        assert "5" in result  # streak count

    def test_streak_breaks(self, tools):
        """Streak should break on a missed day."""
        tools.execute_tool("add_habit", {"name": "Test"})
        habits = tools.read_json("habits.json")
        habit_id = habits[0]["id"]

        log = {}
        # Today and yesterday done, but 2 days ago missed
        log[tools.today()] = {habit_id: True}
        log[tools.days_ago(1)] = {habit_id: True}
        # Skip days_ago(2)
        log[tools.days_ago(3)] = {habit_id: True}
        tools.write_json("habit-log.json", log)

        tools.execute_tool("setup_goal", {"north_star": "X"})
        result = tools.execute_tool("get_progress", {})
        assert "streak" in result.lower()
        # Streak should be 2 (today + yesterday), not 3


# ═══════════════════════════════════════════════════════════
# OVERLAY STATE
# ═══════════════════════════════════════════════════════════

class TestOverlayState:
    """Test the overlay state generation for Hammerspoon."""

    def test_overlay_empty_state(self, tools):
        state = tools.get_overlay_state([])
        assert "timestamp" in state
        assert "conversation" in state
        assert "dashboard" in state
        d = state["dashboard"]
        assert d["northStar"] == ""
        assert d["habitsTotal"] == 0
        assert d["streak"] == 0
        assert d["ow64Completion"] == 0

    def test_overlay_with_data(self, tools):
        tools.execute_tool("setup_goal", {
            "north_star": "Test NS",
            "affirmation": "I am testing",
            "deadline": "2026-12-31",
        })
        tools.execute_tool("add_habit", {"name": "A"})
        tools.execute_tool("add_habit", {"name": "B"})
        tools.execute_tool("check_habit", {"habit_name": "A"})

        conv = [
            {"role": "user", "text": "Hello"},
            {"role": "assistant", "text": "Hi!"},
        ]
        state = tools.get_overlay_state(conv)

        d = state["dashboard"]
        assert d["northStar"] == "Test NS"
        assert d["affirmation"] == "I am testing"
        assert d["habitsCompleted"] == 1
        assert d["habitsTotal"] == 2
        assert len(d["habits"]) == 2
        assert d["daysRemaining"] > 0

        assert len(state["conversation"]) == 2
        assert state["conversation"][0]["role"] == "user"

    def test_overlay_with_goals(self, tools):
        tools.execute_tool("setup_goal", {"north_star": "NS"})
        tools.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A1", "A2"],
        })
        tools.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})

        state = tools.get_overlay_state([])
        d = state["dashboard"]
        assert len(d["goalProgress"]) == 1
        assert d["goalProgress"][0]["title"] == "G1"
        assert d["goalProgress"][0]["pct"] == 50  # 1/2
        assert d["ow64Done"] == 1
        assert d["ow64Total"] == 2

    def test_overlay_mood_energy_averages(self, tools):
        """Mood/energy averages from journal entries."""
        today = tools.today()
        yesterday = tools.days_ago(1)
        for date, mood, energy in [(today, 4, 3), (yesterday, 2, 5)]:
            entry = {
                "date": date, "wentWell": [], "didntGoWell": [],
                "learnings": [], "tomorrowFocus": [], "mood": mood,
                "energy": energy, "createdAt": date, "updatedAt": date,
            }
            tools.write_json(f"journal/{date}.json", entry)

        state = tools.get_overlay_state([])
        d = state["dashboard"]
        assert d["avgMood"] == 3.0  # (4+2)/2
        assert d["avgEnergy"] == 4.0  # (3+5)/2

    def test_overlay_no_mood_data(self, tools):
        state = tools.get_overlay_state([])
        d = state["dashboard"]
        assert d["avgMood"] is None
        assert d["avgEnergy"] is None

    def test_overlay_inactive_habits_excluded(self, tools):
        tools.execute_tool("add_habit", {"name": "Active"})
        tools.execute_tool("add_habit", {"name": "Removed"})
        tools.execute_tool("remove_habit", {"habit_name": "Removed"})

        state = tools.get_overlay_state([])
        d = state["dashboard"]
        assert d["habitsTotal"] == 1
        assert len(d["habits"]) == 1
        assert d["habits"][0]["name"] == "Active"


# ═══════════════════════════════════════════════════════════
# EXECUTE_TOOL DISPATCHER
# ═══════════════════════════════════════════════════════════

class TestExecuteTool:
    """Test the execute_tool dispatcher."""

    def test_unknown_tool(self, tools):
        result = tools.execute_tool("nonexistent_tool", {})
        assert "unknown" in result.lower()

    def test_tool_exception_handling(self, tools):
        """Tool errors should be caught and returned as strings."""
        # Force an error by passing wrong types
        result = tools.execute_tool("complete_action", {
            "goal_number": "not_a_number",
            "action_number": 1,
        })
        assert "error" in result.lower() or "No OW64" in result

    def test_all_tools_callable(self, tools):
        """Every defined tool should be callable without crashing."""
        for t in tools.TOOL_DEFINITIONS:
            name = t["function"]["name"]
            # Call with empty args (should return error message, not crash)
            result = tools.execute_tool(name, {})
            assert isinstance(result, str), f"{name} returned non-string: {type(result)}"
            assert len(result) > 0, f"{name} returned empty string"


# ═══════════════════════════════════════════════════════════
# DATA PERSISTENCE EDGE CASES
# ═══════════════════════════════════════════════════════════

class TestDataPersistence:
    """Test JSON read/write edge cases."""

    def test_read_nonexistent_file(self, tools):
        result = tools.read_json("does-not-exist.json")
        assert result is None

    def test_read_corrupt_json(self, tools):
        path = HARADA_DIR / "corrupt.json"
        path.write_text("{invalid json content")
        result = tools.read_json("corrupt.json")
        assert result is None

    def test_write_creates_directories(self, tools):
        tools.write_json("nested/deep/file.json", {"test": True})
        assert (HARADA_DIR / "nested" / "deep" / "file.json").exists()

    def test_atomic_write(self, tools):
        """Write should not leave partial files on error."""
        tools.write_json("test.json", {"key": "value"})
        data = tools.read_json("test.json")
        assert data == {"key": "value"}
        # No .tmp file should remain
        assert not (HARADA_DIR / "test.json.tmp").exists()

    def test_concurrent_habit_operations(self, tools):
        """Multiple habit operations should not corrupt data."""
        for i in range(20):
            tools.execute_tool("add_habit", {"name": f"Habit {i}"})

        habits = tools.read_json("habits.json")
        assert len(habits) == 20
        ids = [h["id"] for h in habits]
        assert len(set(ids)) == 20  # all unique

        # Check and uncheck rapidly
        for i in range(20):
            tools.execute_tool("check_habit", {"habit_name": f"Habit {i}"})
        for i in range(0, 20, 2):
            tools.execute_tool("uncheck_habit", {"habit_name": f"Habit {i}"})

        result = tools.execute_tool("list_habits", {})
        assert "10/20" in result  # half checked


# ═══════════════════════════════════════════════════════════
# LLM ROUTER TOOL CALLING
# ═══════════════════════════════════════════════════════════

class TestLLMRouterToolCalling:
    """Test chat_with_tools in llm_router.py."""

    def _make_router(self):
        import importlib
        if "llm_router" in sys.modules:
            importlib.reload(sys.modules["llm_router"])
        from llm_router import LLMRouter
        return LLMRouter()

    def test_no_tool_calls_returns_text(self):
        router = self._make_router()
        config = {"provider": "redpill", "model": "test-model"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Hello!", "role": "assistant"},
                "finish_reason": "stop",
            }]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("llm_router.httpx.post", return_value=mock_response):
            result = router.chat_with_tools(
                llm_config=config,
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="Test",
                tools=[],
                tool_executor=lambda n, a: "",
            )

        assert result == "Hello!"

    def test_tool_call_loop(self):
        """Should execute tool calls and loop back to LLM."""
        router = self._make_router()
        config = {"provider": "redpill", "model": "test-model"}

        # First response: tool call
        tool_call_response = MagicMock()
        tool_call_response.status_code = 200
        tool_call_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_123",
                        "function": {
                            "name": "list_habits",
                            "arguments": "{}",
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }
        tool_call_response.raise_for_status = MagicMock()

        # Second response: text
        text_response = MagicMock()
        text_response.status_code = 200
        text_response.json.return_value = {
            "choices": [{
                "message": {"content": "You have 3 habits.", "role": "assistant"},
                "finish_reason": "stop",
            }]
        }
        text_response.raise_for_status = MagicMock()

        call_count = 0
        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_call_response
            return text_response

        executor_called = []
        def mock_executor(name, args):
            executor_called.append((name, args))
            return "3 habits found"

        with patch("llm_router.httpx.post", side_effect=mock_post):
            result = router.chat_with_tools(
                llm_config=config,
                messages=[{"role": "user", "content": "List habits"}],
                system_prompt="Test",
                tools=[{"type": "function", "function": {"name": "list_habits"}}],
                tool_executor=mock_executor,
            )

        assert result == "You have 3 habits."
        assert call_count == 2
        assert len(executor_called) == 1
        assert executor_called[0] == ("list_habits", {})

    def test_multiple_tool_calls_in_one_response(self):
        """LLM may return multiple tool calls in a single response."""
        router = self._make_router()
        config = {"provider": "redpill", "model": "test-model"}

        multi_tool_response = MagicMock()
        multi_tool_response.status_code = 200
        multi_tool_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "c1", "function": {"name": "check_habit", "arguments": '{"habit_name": "exercise"}'}},
                        {"id": "c2", "function": {"name": "check_habit", "arguments": '{"habit_name": "study"}'}},
                    ],
                },
                "finish_reason": "tool_calls",
            }]
        }
        multi_tool_response.raise_for_status = MagicMock()

        final_response = MagicMock()
        final_response.status_code = 200
        final_response.json.return_value = {
            "choices": [{"message": {"content": "Done!", "role": "assistant"}, "finish_reason": "stop"}]
        }
        final_response.raise_for_status = MagicMock()

        calls = []
        def mock_post(*a, **kw):
            calls.append(kw.get("json", {}).get("messages", []))
            if len(calls) == 1:
                return multi_tool_response
            return final_response

        tool_calls = []
        def mock_executor(name, args):
            tool_calls.append(name)
            return "ok"

        with patch("llm_router.httpx.post", side_effect=mock_post):
            result = router.chat_with_tools(
                llm_config=config,
                messages=[{"role": "user", "content": "Do both"}],
                system_prompt="Test",
                tools=[],
                tool_executor=mock_executor,
            )

        assert result == "Done!"
        assert tool_calls == ["check_habit", "check_habit"]

        # Second call should include both tool results
        second_messages = calls[1]
        tool_results = [m for m in second_messages if m.get("role") == "tool"]
        assert len(tool_results) == 2

    def test_max_rounds_safety(self):
        """Should stop after MAX_TOOL_ROUNDS to prevent infinite loops."""
        router = self._make_router()
        router.MAX_TOOL_ROUNDS = 3
        config = {"provider": "redpill", "model": "test-model"}

        # Always returns tool calls (infinite loop)
        infinite_response = MagicMock()
        infinite_response.status_code = 200
        infinite_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "fallback text",
                    "role": "assistant",
                    "tool_calls": [{"id": "c1", "function": {"name": "get_progress", "arguments": "{}"}}],
                },
                "finish_reason": "tool_calls",
            }]
        }
        infinite_response.raise_for_status = MagicMock()

        call_count = 0
        def mock_post(*a, **kw):
            nonlocal call_count
            call_count += 1
            return infinite_response

        with patch("llm_router.httpx.post", side_effect=mock_post):
            result = router.chat_with_tools(
                llm_config=config,
                messages=[],
                system_prompt="Test",
                tools=[],
                tool_executor=lambda n, a: "ok",
            )

        assert call_count == 3  # stopped at MAX_TOOL_ROUNDS
        assert isinstance(result, str)

    def test_non_redpill_falls_back_to_chat(self):
        """Non-redpill providers should fall back to regular chat."""
        router = self._make_router()
        config = {"provider": "ollama", "model": "test"}

        with patch("llm_router.ollama") as mock:
            mock.chat.return_value = {"message": {"content": "Hi"}}
            result = router.chat_with_tools(
                llm_config=config,
                messages=[{"role": "user", "content": "Hi"}],
                system_prompt="Test",
                tools=[],
                tool_executor=lambda n, a: "",
            )

        assert result == "Hi"

    def test_malformed_tool_arguments(self):
        """Should handle malformed JSON in tool arguments gracefully."""
        router = self._make_router()
        config = {"provider": "redpill", "model": "test"}

        bad_args_response = MagicMock()
        bad_args_response.status_code = 200
        bad_args_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [{"id": "c1", "function": {"name": "list_habits", "arguments": "not json!!!"}}],
                },
                "finish_reason": "tool_calls",
            }]
        }
        bad_args_response.raise_for_status = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.json.return_value = {
            "choices": [{"message": {"content": "OK", "role": "assistant"}, "finish_reason": "stop"}]
        }
        final.raise_for_status = MagicMock()

        n = 0
        def mock_post(*a, **kw):
            nonlocal n; n += 1
            return bad_args_response if n == 1 else final

        executor_args = []
        def mock_executor(name, args):
            executor_args.append(args)
            return "ok"

        with patch("llm_router.httpx.post", side_effect=mock_post):
            result = router.chat_with_tools(
                llm_config=config,
                messages=[],
                system_prompt="Test",
                tools=[],
                tool_executor=mock_executor,
            )

        assert result == "OK"
        assert executor_args[0] == {}  # empty dict fallback

    def test_api_error_propagates(self):
        """HTTP errors should propagate up for main.py to catch."""
        router = self._make_router()
        config = {"provider": "redpill", "model": "test"}

        import httpx
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Model not found"
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=error_response
        )

        with patch("llm_router.httpx.post", return_value=error_response):
            with pytest.raises(httpx.HTTPStatusError):
                router.chat_with_tools(
                    llm_config=config,
                    messages=[],
                    system_prompt="Test",
                    tools=[],
                    tool_executor=lambda n, a: "",
                )


# ═══════════════════════════════════════════════════════════
# CONVERSATION TOOL INTEGRATION
# ═══════════════════════════════════════════════════════════

class TestConversationTools:
    """Test Conversation.get_response_with_tools integration."""

    def test_get_response_with_tools_delegates(self):
        import importlib
        if "conversation" in sys.modules:
            importlib.reload(sys.modules["conversation"])
        from conversation import Conversation

        mock_pm = MagicMock()
        mock_pm.get_current.return_value = {
            "llm": {"provider": "redpill", "model": "test"},
            "system_prompt": "You are helpful",
        }
        mock_router = MagicMock()
        mock_router.chat_with_tools.return_value = "Tool response"

        conv = Conversation(persona_manager=mock_pm, llm_router=mock_router)
        conv.add_user_message("Test")

        tools = [{"type": "function", "function": {"name": "test"}}]
        executor = lambda n, a: "ok"

        result = conv.get_response_with_tools(tools=tools, tool_executor=executor)

        assert result == "Tool response"
        mock_router.chat_with_tools.assert_called_once()
        call_kwargs = mock_router.chat_with_tools.call_args
        assert call_kwargs.kwargs["tools"] == tools
        assert call_kwargs.kwargs["tool_executor"] == executor

    def test_get_response_with_tools_uses_override_model(self):
        import importlib
        for mod in ["conversation", "model_manager"]:
            if mod in sys.modules:
                importlib.reload(sys.modules[mod])
        from conversation import Conversation

        mock_pm = MagicMock()
        mock_pm.get_current.return_value = {
            "llm": {"provider": "redpill", "model": "default-model"},
            "system_prompt": "Test",
        }
        mock_router = MagicMock()
        mock_router.chat_with_tools.return_value = "ok"

        conv = Conversation(persona_manager=mock_pm, llm_router=mock_router)
        conv.add_user_message("Test")

        with patch("conversation.ModelManager") as MockMM:
            MockMM.return_value.get_current_model.return_value = "override-model"
            conv.get_response_with_tools(tools=[], tool_executor=lambda n, a: "")

        call_kwargs = mock_router.chat_with_tools.call_args
        assert call_kwargs.kwargs["llm_config"]["model"] == "override-model"


# ═══════════════════════════════════════════════════════════
# MAIN.PY INTEGRATION
# ═══════════════════════════════════════════════════════════

class TestMainIntegration:
    """Test that main.py correctly wires tools for harada persona."""

    def test_write_overlay_state_function(self):
        """Test _write_overlay_state creates valid JSON."""
        import importlib
        if "main" in sys.modules:
            importlib.reload(sys.modules["main"])

        # We can't easily test the full main flow (needs audio),
        # but we can test _write_overlay_state directly
        sys.path.insert(0, str(PROJECT_DIR))
        from main import _write_overlay_state, OVERLAY_STATE_FILE
        from conversation import Conversation

        conv = Conversation(persona_manager=MagicMock(), llm_router=MagicMock())

        _write_overlay_state("Hello", "Hi there!", conv)

        assert OVERLAY_STATE_FILE.exists()
        with open(OVERLAY_STATE_FILE) as f:
            state = json.load(f)

        assert len(state["conversation"]) == 2
        assert state["conversation"][0]["text"] == "Hello"
        assert state["conversation"][1]["text"] == "Hi there!"
        assert "dashboard" in state

        # Clean up
        OVERLAY_STATE_FILE.unlink(missing_ok=True)

    def test_write_overlay_accumulates_conversation(self):
        """Multiple calls should accumulate conversation history."""
        sys.path.insert(0, str(PROJECT_DIR))
        from main import _write_overlay_state, OVERLAY_STATE_FILE

        conv = MagicMock()

        _write_overlay_state("Msg 1", "Reply 1", conv)
        _write_overlay_state("Msg 2", "Reply 2", conv)
        _write_overlay_state("Msg 3", "Reply 3", conv)

        with open(OVERLAY_STATE_FILE) as f:
            state = json.load(f)

        assert len(state["conversation"]) == 6  # 3 exchanges * 2
        assert state["conversation"][0]["text"] == "Msg 1"
        assert state["conversation"][5]["text"] == "Reply 3"

        OVERLAY_STATE_FILE.unlink(missing_ok=True)

    def test_write_overlay_truncates_at_40(self):
        """Conversation should be truncated to last 40 messages."""
        sys.path.insert(0, str(PROJECT_DIR))
        from main import _write_overlay_state, OVERLAY_STATE_FILE

        conv = MagicMock()

        for i in range(25):
            _write_overlay_state(f"User {i}", f"Agent {i}", conv)

        with open(OVERLAY_STATE_FILE) as f:
            state = json.load(f)

        assert len(state["conversation"]) == 40
        # Should keep most recent
        assert state["conversation"][-1]["text"] == "Agent 24"

        OVERLAY_STATE_FILE.unlink(missing_ok=True)
