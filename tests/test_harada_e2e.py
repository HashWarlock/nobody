"""End-to-end simulation tests for Harada voice agent.

Mocks the RedPill API to simulate real model behaviors across different
models and conversation scenarios. Tests the full pipeline:
  transcript → persona detection → LLM with tools → tool execution → response → overlay

No live API calls — all model responses are simulated based on real
OpenAI-compatible API response formats.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Mock ollama before imports
mock_ollama = MagicMock()
sys.modules["ollama"] = mock_ollama

PROJECT_DIR = Path(__file__).parent.parent
HARADA_DIR = PROJECT_DIR / ".pi" / "harada"
HARADA_TEST_BACKUP = PROJECT_DIR / ".pi" / "harada_e2e_backup"
OVERLAY_FILE = Path("/tmp/claude/voice-realtime/harada-overlay.json")


@pytest.fixture(autouse=True)
def clean_state():
    """Clean harada data and overlay file for each test."""
    # Backup existing
    if HARADA_DIR.exists():
        if HARADA_TEST_BACKUP.exists():
            shutil.rmtree(HARADA_TEST_BACKUP)
        shutil.copytree(HARADA_DIR, HARADA_TEST_BACKUP)
        shutil.rmtree(HARADA_DIR)
    HARADA_DIR.mkdir(parents=True, exist_ok=True)
    (HARADA_DIR / "journal").mkdir(exist_ok=True)

    # Clean overlay
    overlay_backup = None
    if OVERLAY_FILE.exists():
        overlay_backup = OVERLAY_FILE.read_text()
        OVERLAY_FILE.unlink()

    yield

    # Restore
    if HARADA_DIR.exists():
        shutil.rmtree(HARADA_DIR)
    if HARADA_TEST_BACKUP.exists():
        shutil.copytree(HARADA_TEST_BACKUP, HARADA_DIR)
        shutil.rmtree(HARADA_TEST_BACKUP)
    if overlay_backup:
        OVERLAY_FILE.write_text(overlay_backup)
    elif OVERLAY_FILE.exists():
        OVERLAY_FILE.unlink()


@pytest.fixture
def tools_module():
    """Fresh import of harada_tools."""
    import importlib
    if "harada_tools" in sys.modules:
        importlib.reload(sys.modules["harada_tools"])
    import harada_tools
    return harada_tools


@pytest.fixture
def router():
    """Fresh LLMRouter."""
    import importlib
    if "llm_router" in sys.modules:
        importlib.reload(sys.modules["llm_router"])
    from llm_router import LLMRouter
    return LLMRouter()


# ═══════════════════════════════════════════════════════════
# API Response Helpers
# ═══════════════════════════════════════════════════════════

def _make_text_response(content, finish_reason="stop"):
    """Create a mock API response with text content."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{
            "message": {"content": content, "role": "assistant"},
            "finish_reason": finish_reason,
        }]
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_tool_response(tool_calls, content=None, finish_reason="tool_calls"):
    """Create a mock API response with tool calls.

    tool_calls: list of (name, args_dict) tuples
    """
    tc_list = []
    for i, (name, args) in enumerate(tool_calls):
        tc_list.append({
            "id": f"call_{name}_{i}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args) if isinstance(args, dict) else args,
            },
        })

    msg = {
        "content": content,
        "role": "assistant",
        "tool_calls": tc_list,
    }

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{
            "message": msg,
            "finish_reason": finish_reason,
        }]
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_error_response(status_code, message):
    """Create a mock error response."""
    import httpx
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps({"error": {"message": message}})
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        str(status_code), request=MagicMock(), response=resp
    )
    return resp


def _run_chat_with_tools(router, responses, model="z-ai/glm-5"):
    """Run chat_with_tools with a sequence of mock API responses.

    Returns the final text response.
    """
    from harada_tools import TOOL_DEFINITIONS, execute_tool

    call_idx = [0]
    def mock_post(*args, **kwargs):
        idx = call_idx[0]
        call_idx[0] += 1
        if idx < len(responses):
            return responses[idx]
        return _make_text_response("(fallback)")

    with patch("llm_router.httpx.post", side_effect=mock_post):
        result = router.chat_with_tools(
            llm_config={"provider": "redpill", "model": model},
            messages=[{"role": "user", "content": "test"}],
            system_prompt="You are a coach.",
            tools=TOOL_DEFINITIONS,
            tool_executor=execute_tool,
        )
    return result


# ═══════════════════════════════════════════════════════════
# SCENARIO 1: First-Time User — Full Onboarding
# ═══════════════════════════════════════════════════════════

class TestOnboardingScenario:
    """Simulate a new user setting up their Harada goal for the first time."""

    def test_greeting_checks_state(self, router, tools_module):
        """Model should call get_progress/get_affirmation on greeting and find nothing."""
        responses = [
            # Round 1: model calls get_affirmation
            _make_tool_response([("get_affirmation", {})]),
            # Round 2: sees "no affirmation", responds with onboarding prompt
            _make_text_response(
                "Welcome! I'm your Harada coach. What's the one thing you want to achieve more than anything?"
            ),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "achieve" in result.lower() or "welcome" in result.lower()

    def test_setup_goal_from_voice(self, router, tools_module):
        """User states their goal, model calls setup_goal."""
        responses = [
            _make_tool_response([("setup_goal", {
                "north_star": "Run a marathon",
                "affirmation": "I am a strong and capable runner",
                "deadline": "2026-12-01",
            })]),
            _make_text_response("Great! Your north star is set: run a marathon by December. Let's break that down into supporting goals."),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "marathon" in result.lower()

        # Verify data persisted
        gf = tools_module._read_json("goal-form.json")
        assert gf["northStar"] == "Run a marathon"
        assert gf["affirmation"] == "I am a strong and capable runner"
        assert gf["deadline"] == "2026-12-01"

    def test_setup_goals_and_habits_multi_turn(self, router, tools_module):
        """Full onboarding: goal → supporting goal → habits, all via tool calls."""
        # Pre-setup goal (from previous turn)
        tools_module.execute_tool("setup_goal", {
            "north_star": "Run a marathon",
            "deadline": "2026-12-01",
        })

        # Turn 1: Setup supporting goal
        responses = [
            _make_tool_response([("setup_supporting_goal", {
                "goal_number": 1,
                "title": "Build endurance",
                "actions": ["Run 3 times a week", "Increase distance by 10% weekly", "Do a half marathon"],
            })]),
            _make_text_response("First pillar set: build endurance. What's another area to focus on?"),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "endurance" in result.lower()

        # Turn 2: Add habits
        responses = [
            _make_tool_response([
                ("add_habit", {"name": "Morning run"}),
                ("add_habit", {"name": "Stretch routine"}),
                ("add_habit", {"name": "Track calories"}),
            ]),
            _make_text_response("Added 3 daily habits. You're all set! Want to check one off?"),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "habits" in result.lower() or "set" in result.lower()

        # Verify
        habits = tools_module._read_json("habits.json")
        assert len(habits) == 3
        ow64 = tools_module._read_json("ow64.json")
        assert ow64["supportingGoals"][0]["title"] == "Build endurance"


# ═══════════════════════════════════════════════════════════
# SCENARIO 2: Daily Check-in
# ═══════════════════════════════════════════════════════════

class TestDailyCheckinScenario:
    """Simulate a returning user doing their morning check-in."""

    @pytest.fixture(autouse=True)
    def setup_user_data(self, tools_module):
        """Create realistic user data."""
        tools_module.execute_tool("setup_goal", {
            "north_star": "Become a senior engineer",
            "affirmation": "I am growing every day into a world-class engineer",
            "deadline": "2027-06-01",
        })
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "Deep technical skills",
            "actions": ["Complete system design course", "Read DDIA book", "Build distributed system project"],
        })
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 2, "title": "Leadership",
            "actions": ["Lead a team project", "Give tech talk", "Mentor junior dev"],
        })
        tools_module.execute_tool("add_habit", {"name": "Read 30 min"})
        tools_module.execute_tool("add_habit", {"name": "Exercise"})
        tools_module.execute_tool("add_habit", {"name": "Code practice"})
        tools_module.execute_tool("add_habit", {"name": "Review goals"})

    def test_morning_greeting_with_affirmation(self, router, tools_module):
        """Coach greets with affirmation and habit status."""
        responses = [
            # Model calls get_affirmation + list_habits
            _make_tool_response([
                ("get_affirmation", {}),
                ("list_habits", {}),
            ]),
            _make_text_response(
                "Good morning! Remember: I am growing every day. You have 4 habits to tackle today. Let's get started!"
            ),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "growing" in result.lower() or "morning" in result.lower()

    def test_check_multiple_habits_by_voice(self, router, tools_module):
        """User says 'I exercised and read today', model checks both."""
        responses = [
            _make_tool_response([
                ("check_habit", {"habit_name": "exercise"}),
                ("check_habit", {"habit_name": "read"}),
            ]),
            _make_text_response("Nice work! Exercise and reading checked. 2 out of 4 done. Keep it up!"),
        ]
        result = _run_chat_with_tools(router, responses)

        # Verify both habits are checked
        log = tools_module._read_json("habit-log.json")
        today = tools_module._today()
        habits = tools_module._read_json("habits.json")
        exercise = next(h for h in habits if h["name"] == "Exercise")
        read = next(h for h in habits if h["name"] == "Read 30 min")
        assert log[today][exercise["id"]] is True
        assert log[today][read["id"]] is True

    def test_check_all_habits_celebration(self, router, tools_module):
        """Checking all 4 habits should trigger celebration."""
        # Pre-check 3 habits
        tools_module.execute_tool("check_habit", {"habit_name": "exercise"})
        tools_module.execute_tool("check_habit", {"habit_name": "read"})
        tools_module.execute_tool("check_habit", {"habit_name": "code"})

        # Check last one
        responses = [
            _make_tool_response([("check_habit", {"habit_name": "review goals"})]),
            _make_text_response("All 4 habits done! You're crushing it today! 🎉"),
        ]
        result = _run_chat_with_tools(router, responses)

        # All should be checked
        log = tools_module._read_json("habit-log.json")
        today = tools_module._today()
        habits = tools_module._read_json("habits.json")
        for h in habits:
            assert log[today].get(h["id"]) is True

    def test_progress_check(self, router, tools_module):
        """User asks 'how am I doing?'"""
        tools_module.execute_tool("check_habit", {"habit_name": "exercise"})
        tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})

        responses = [
            _make_tool_response([("get_progress", {})]),
            _make_text_response("You're on track! 1 of 4 habits done today, and you've completed your system design course action."),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "track" in result.lower() or "habit" in result.lower()


# ═══════════════════════════════════════════════════════════
# SCENARIO 3: Evening Journal
# ═══════════════════════════════════════════════════════════

class TestJournalingScenario:
    """Simulate evening reflection/journaling via voice."""

    @pytest.fixture(autouse=True)
    def setup_goal(self, tools_module):
        tools_module.execute_tool("setup_goal", {
            "north_star": "Launch startup",
            "affirmation": "I am building something meaningful",
        })
        tools_module.execute_tool("add_habit", {"name": "Meditate"})
        tools_module.execute_tool("add_habit", {"name": "Network"})

    def test_journal_entry_from_reflection(self, router, tools_module):
        """Coach guides reflection and writes journal."""
        responses = [
            _make_tool_response([("write_journal", {
                "went_well": ["Had a great meeting with investors", "Shipped MVP feature"],
                "didnt_go_well": ["Missed gym again"],
                "learnings": ["Need to schedule exercise, not just hope for it"],
                "mood": 4,
                "energy": 3,
            })]),
            _make_text_response("Journal saved! Sounds like a productive day. I noticed the gym keeps slipping — maybe we should make it a scheduled habit?"),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "journal" in result.lower() or "saved" in result.lower()

        # Verify journal persisted
        today = tools_module._today()
        entry = tools_module._read_json(f"journal/{today}.json")
        assert entry is not None
        assert "great meeting" in entry["wentWell"][0].lower()
        assert entry["mood"] == 4
        assert entry["energy"] == 3

    def test_journal_update_preserves_earlier_data(self, router, tools_module):
        """Updating journal later in the day should preserve earlier entries."""
        # Morning entry
        tools_module.execute_tool("write_journal", {
            "went_well": ["Morning run completed"],
            "mood": 5,
            "energy": 5,
        })

        # Evening update — only adds learnings, preserves morning data
        responses = [
            _make_tool_response([("write_journal", {
                "learnings": ["Consistency is everything"],
                "didnt_go_well": ["Afternoon slump"],
            })]),
            _make_text_response("Added your evening reflections. Mood staying at great!"),
        ]
        _run_chat_with_tools(router, responses)

        today = tools_module._today()
        entry = tools_module._read_json(f"journal/{today}.json")
        # Evening data
        assert "Consistency" in entry["learnings"][0]
        assert "slump" in entry["didntGoWell"][0].lower()
        # Morning data preserved
        assert entry["mood"] == 5  # preserved from morning
        assert entry["energy"] == 5  # preserved from morning

    def test_read_past_journal(self, router, tools_module):
        """User asks to review yesterday's journal."""
        # Write a past journal entry directly
        yesterday = tools_module._days_ago(1)
        tools_module._write_json(f"journal/{yesterday}.json", {
            "date": yesterday,
            "wentWell": ["Closed a deal"],
            "didntGoWell": [],
            "learnings": ["Persistence pays off"],
            "tomorrowFocus": [],
            "mood": 5,
            "energy": 4,
            "createdAt": yesterday,
            "updatedAt": yesterday,
        })

        responses = [
            _make_tool_response([("read_journal", {"date": yesterday})]),
            _make_text_response(f"Yesterday was a great day! You closed a deal and learned that persistence pays off. Mood was 5/5!"),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "persistence" in result.lower() or "deal" in result.lower()


# ═══════════════════════════════════════════════════════════
# SCENARIO 4: Multi-Model Behavior Simulation
# ═══════════════════════════════════════════════════════════

class TestModelBehaviors:
    """Simulate how different models handle tool calling.

    Models differ in:
    - Whether they use tool calls or try to do everything in text
    - How they format arguments (strict JSON vs. sloppy)
    - Number of tool calls per response
    - finish_reason values
    """

    @pytest.fixture(autouse=True)
    def setup_data(self, tools_module):
        tools_module.execute_tool("setup_goal", {"north_star": "Test", "affirmation": "I am testing"})
        tools_module.execute_tool("add_habit", {"name": "Run"})
        tools_module.execute_tool("add_habit", {"name": "Read"})

    def test_glm5_standard_tool_call(self, router, tools_module):
        """GLM-5: Standard behavior — single tool call per turn."""
        responses = [
            _make_tool_response([("check_habit", {"habit_name": "run"})]),
            _make_text_response("Great, running checked off! 1 of 2 done."),
        ]
        result = _run_chat_with_tools(router, responses, model="z-ai/glm-5")
        assert "checked" in result.lower() or "done" in result.lower()

    def test_kimi_k25_parallel_tool_calls(self, router, tools_module):
        """Kimi K2.5: Aggressive — calls multiple tools in parallel."""
        responses = [
            _make_tool_response([
                ("check_habit", {"habit_name": "run"}),
                ("check_habit", {"habit_name": "read"}),
                ("get_progress", {}),
            ]),
            _make_text_response("All done! Both habits checked and you're making great progress."),
        ]
        result = _run_chat_with_tools(router, responses, model="moonshotai/kimi-k2.5")
        assert "done" in result.lower() or "progress" in result.lower()

        # Both habits should be checked
        log = tools_module._read_json("habit-log.json")
        today = tools_module._today()
        habits = tools_module._read_json("habits.json")
        for h in habits:
            assert log[today].get(h["id"]) is True

    def test_deepseek_multi_round_tool_calls(self, router, tools_module):
        """DeepSeek: Makes multiple sequential rounds of tool calls."""
        responses = [
            # Round 1: check state
            _make_tool_response([("get_progress", {})]),
            # Round 2: now act on it
            _make_tool_response([("check_habit", {"habit_name": "run"})]),
            # Round 3: text response
            _make_text_response("You're at 1/2 habits today after checking off your run."),
        ]
        result = _run_chat_with_tools(router, responses, model="deepseek/deepseek-v3.2")
        assert "run" in result.lower() or "habit" in result.lower()

    def test_llama_sloppy_json_args(self, router, tools_module):
        """Llama 3.3: May produce slightly malformed JSON in arguments."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "check_habit",
                            # Note: arguments as dict instead of string (some models do this)
                            "arguments": {"habit_name": "run"},
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }
        resp.raise_for_status = MagicMock()

        responses = [resp, _make_text_response("Run checked! Nice.")]
        result = _run_chat_with_tools(router, responses, model="meta-llama/llama-3.3-70b-instruct")
        assert "nice" in result.lower() or "checked" in result.lower()

    def test_model_returns_content_with_tool_calls(self, router, tools_module):
        """Some models return both content AND tool_calls."""
        responses = [
            _make_tool_response(
                [("check_habit", {"habit_name": "run"})],
                content="Let me check that for you...",  # content alongside tool calls
            ),
            _make_text_response("Done! Run is checked off."),
        ]
        result = _run_chat_with_tools(router, responses)
        assert "done" in result.lower() or "checked" in result.lower()

    def test_model_returns_empty_tool_call_list(self, router, tools_module):
        """Edge: model returns tool_calls as empty list."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Sure, your habits look good!",
                    "role": "assistant",
                    "tool_calls": [],  # empty
                },
                "finish_reason": "stop",
            }]
        }
        resp.raise_for_status = MagicMock()

        responses = [resp]
        result = _run_chat_with_tools(router, responses)
        assert "habits" in result.lower()

    def test_model_finish_reason_stop_with_tool_calls(self, router, tools_module):
        """Edge: model returns tool_calls but finish_reason='stop' (should treat as no tool calls)."""
        responses = [
            _make_tool_response(
                [("check_habit", {"habit_name": "run"})],
                content="Checked!",
                finish_reason="stop",  # stop should override tool_calls
            ),
        ]
        result = _run_chat_with_tools(router, responses)
        # Should return the content without executing tool calls
        assert result == "Checked!"

    def test_model_no_content_no_tool_calls(self, router, tools_module):
        """Edge: model returns neither content nor tool_calls."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{
                "message": {"content": None, "role": "assistant"},
                "finish_reason": "stop",
            }]
        }
        resp.raise_for_status = MagicMock()

        responses = [resp]
        result = _run_chat_with_tools(router, responses)
        assert result == "" or result is None  # graceful empty

    def test_model_returns_malformed_json_arguments(self, router, tools_module):
        """Model returns completely invalid JSON in arguments."""
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{
                "message": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "list_habits",
                            "arguments": "let me list the habits for you",  # not JSON
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }
        resp.raise_for_status = MagicMock()

        responses = [resp, _make_text_response("Here are your habits.")]
        result = _run_chat_with_tools(router, responses)
        # Should not crash — falls back to {} args
        assert "habits" in result.lower()


# ═══════════════════════════════════════════════════════════
# SCENARIO 5: Error Handling & Recovery
# ═══════════════════════════════════════════════════════════

class TestErrorRecovery:
    """Test graceful handling of API errors, timeouts, and edge cases."""

    def test_402_quota_exceeded(self, router, tools_module):
        """Should propagate 402 error for main.py try/except to catch."""
        import httpx
        responses = [_make_error_response(402, "Account quota exceeded")]

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            _run_chat_with_tools(router, responses)
        assert "402" in str(exc_info.value)

    def test_429_rate_limit(self, router, tools_module):
        """Should propagate 429 rate limit."""
        import httpx
        responses = [_make_error_response(429, "Rate limit exceeded")]

        with pytest.raises(httpx.HTTPStatusError):
            _run_chat_with_tools(router, responses)

    def test_500_server_error(self, router, tools_module):
        """Should propagate 500 server error."""
        import httpx
        responses = [_make_error_response(500, "Internal server error")]

        with pytest.raises(httpx.HTTPStatusError):
            _run_chat_with_tools(router, responses)

    def test_404_model_not_found(self, router, tools_module):
        """Should propagate 404 for invalid model ID."""
        import httpx
        responses = [_make_error_response(404, "Model 'fake-model' not found")]

        with pytest.raises(httpx.HTTPStatusError):
            _run_chat_with_tools(router, responses, model="fake-model")

    def test_timeout(self, router, tools_module):
        """Network timeout should raise RequestError."""
        import httpx

        def timeout_post(*args, **kwargs):
            raise httpx.ReadTimeout("Read timed out")

        with patch("llm_router.httpx.post", side_effect=timeout_post):
            with pytest.raises(httpx.ReadTimeout):
                router.chat_with_tools(
                    llm_config={"provider": "redpill", "model": "test"},
                    messages=[{"role": "user", "content": "hi"}],
                    system_prompt="test",
                    tools=[],
                    tool_executor=lambda n, a: "",
                )

    def test_tool_execution_error_doesnt_crash_loop(self, router, tools_module):
        """If a tool raises an error, the error message should be sent back to the LLM."""
        from harada_tools import TOOL_DEFINITIONS

        def bad_executor(name, args):
            if name == "check_habit":
                raise RuntimeError("Database connection failed")
            return "ok"

        # Model calls check_habit, executor raises, error goes back as tool result
        call_log = []
        def mock_post(*args, **kwargs):
            payload = kwargs.get("json", {})
            call_log.append(payload)
            if len(call_log) == 1:
                return _make_tool_response([("check_habit", {"habit_name": "run"})])
            return _make_text_response("I'm having trouble checking that habit. Can you try again?")

        # The execute_tool function wraps errors — test that
        from harada_tools import execute_tool
        result = execute_tool("nonexistent", {})
        assert "Unknown tool" in result

        # Test the full loop doesn't crash
        with patch("llm_router.httpx.post", side_effect=mock_post):
            result = router.chat_with_tools(
                llm_config={"provider": "redpill", "model": "test"},
                messages=[{"role": "user", "content": "check run"}],
                system_prompt="test",
                tools=TOOL_DEFINITIONS,
                tool_executor=lambda n, a: execute_tool(n, a),
            )
        assert isinstance(result, str)

    def test_infinite_tool_loop_breaks(self, router, tools_module):
        """Model that always returns tool calls should hit MAX_TOOL_ROUNDS."""
        router.MAX_TOOL_ROUNDS = 3

        responses = [
            _make_tool_response([("list_habits", {})]),
            _make_tool_response([("list_habits", {})]),
            _make_tool_response([("list_habits", {})], content="Still processing..."),
        ]
        result = _run_chat_with_tools(router, responses)
        assert isinstance(result, str)  # should return something, not crash

    def test_error_in_overlay_doesnt_crash_response(self, tools_module):
        """Overlay state generation errors should be caught."""
        from main import _write_overlay_state

        # Mock conversation object
        conv = MagicMock()

        # Even with weird data, should not raise
        _write_overlay_state("hello", "hi", conv)
        assert OVERLAY_FILE.exists()

        # Clean up
        OVERLAY_FILE.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════
# SCENARIO 6: Overlay State Across Full Session
# ═══════════════════════════════════════════════════════════

class TestOverlaySession:
    """Test overlay state accumulation across a multi-turn voice session."""

    @pytest.fixture(autouse=True)
    def setup_data(self, tools_module):
        tools_module.execute_tool("setup_goal", {
            "north_star": "Master ML",
            "affirmation": "I learn deeply every day",
            "deadline": "2027-01-01",
        })
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "Math foundations",
            "actions": ["Linear algebra course", "Probability course"],
        })
        tools_module.execute_tool("add_habit", {"name": "Study math"})
        tools_module.execute_tool("add_habit", {"name": "Read papers"})

    def test_overlay_updates_per_exchange(self, tools_module):
        """Each voice exchange should update the overlay file."""
        from main import _write_overlay_state

        conv = MagicMock()

        # Exchange 1
        _write_overlay_state("Good morning", "Good morning! Your affirmation: I learn deeply every day.", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert len(state["conversation"]) == 2
        assert state["dashboard"]["northStar"] == "Master ML"

        # Exchange 2 — check a habit first
        tools_module.execute_tool("check_habit", {"habit_name": "study math"})
        _write_overlay_state("I studied math today", "Checked off study math! 1 of 2 done.", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert len(state["conversation"]) == 4
        assert state["dashboard"]["habitsCompleted"] == 1
        assert state["dashboard"]["habitsTotal"] == 2

        # Exchange 3 — complete action
        tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})
        _write_overlay_state("I finished the linear algebra course", "Amazing! Action completed.", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert len(state["conversation"]) == 6
        assert state["dashboard"]["ow64Done"] == 1
        assert state["dashboard"]["goalProgress"][0]["pct"] == 50

        OVERLAY_FILE.unlink(missing_ok=True)

    def test_overlay_conversation_truncation(self, tools_module):
        """Overlay should truncate to 40 messages max."""
        from main import _write_overlay_state
        conv = MagicMock()

        for i in range(25):
            _write_overlay_state(f"User message {i}", f"Agent reply {i}", conv)

        state = json.loads(OVERLAY_FILE.read_text())
        assert len(state["conversation"]) == 40
        # Last message should be the most recent
        assert state["conversation"][-1]["text"] == "Agent reply 24"
        # First message should NOT be message 0 (it was truncated)
        assert state["conversation"][0]["text"] == "User message 5"

        OVERLAY_FILE.unlink(missing_ok=True)

    def test_overlay_habit_completion_reflects_live(self, tools_module):
        """Overlay shows real-time habit state after tools execute."""
        from main import _write_overlay_state
        conv = MagicMock()

        # Before any habits checked
        _write_overlay_state("hi", "hello", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert state["dashboard"]["habitsCompleted"] == 0

        # Check one habit
        tools_module.execute_tool("check_habit", {"habit_name": "study"})
        _write_overlay_state("done studying", "Great!", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert state["dashboard"]["habitsCompleted"] == 1

        # Check second habit
        tools_module.execute_tool("check_habit", {"habit_name": "papers"})
        _write_overlay_state("read papers too", "All done!", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert state["dashboard"]["habitsCompleted"] == 2
        assert state["dashboard"]["habitsTotal"] == 2

        OVERLAY_FILE.unlink(missing_ok=True)

    def test_overlay_streak_updates(self, tools_module):
        """Streak should increase when all habits are done for consecutive days."""
        from main import _write_overlay_state
        conv = MagicMock()

        habits = tools_module._read_json("habits.json")
        habit_ids = [h["id"] for h in habits]

        # Simulate 5 days of completed habits
        log = {}
        for i in range(5):
            d = tools_module._days_ago(i)
            log[d] = {hid: True for hid in habit_ids}
        tools_module._write_json("habit-log.json", log)

        _write_overlay_state("how's my streak?", "5 day streak!", conv)
        state = json.loads(OVERLAY_FILE.read_text())
        assert state["dashboard"]["streak"] == 5

        OVERLAY_FILE.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════
# SCENARIO 7: Persona Switching
# ═══════════════════════════════════════════════════════════

class TestPersonaSwitching:
    """Test that tool calling only activates for harada persona."""

    def test_harada_persona_has_tools(self):
        from persona_manager import PersonaManager
        pm = PersonaManager()
        pm.switch("harada")
        p = pm.get_current()
        assert p["enable_tools"] is True
        assert p["tools"] == "harada"

    def test_assistant_persona_no_tools(self):
        from persona_manager import PersonaManager
        pm = PersonaManager()
        pm.switch("assistant")
        p = pm.get_current()
        assert not p.get("enable_tools")
        assert not p.get("tools")

    def test_switching_away_from_harada(self):
        from persona_manager import PersonaManager
        pm = PersonaManager()
        pm.switch("harada")
        assert pm.get_current()["enable_tools"] is True
        pm.switch("assistant")
        assert not pm.get_current().get("enable_tools")

    def test_non_redpill_provider_skips_tools(self, router):
        """Ollama provider should skip tool calling and use regular chat."""
        with patch("llm_router.ollama") as mock:
            mock.chat.return_value = {"message": {"content": "Regular response"}}
            result = router.chat_with_tools(
                llm_config={"provider": "ollama", "model": "llama3.1:8b"},
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="test",
                tools=[{"type": "function", "function": {"name": "test"}}],
                tool_executor=lambda n, a: "should not be called",
            )
        assert result == "Regular response"


# ═══════════════════════════════════════════════════════════
# SCENARIO 8: Edge Cases in Tool Arguments
# ═══════════════════════════════════════════════════════════

class TestToolArgumentEdgeCases:
    """Test unusual argument patterns that models might produce."""

    @pytest.fixture(autouse=True)
    def setup_data(self, tools_module):
        tools_module.execute_tool("setup_goal", {"north_star": "Test"})
        tools_module.execute_tool("add_habit", {"name": "Exercise"})

    def test_extra_arguments_ignored(self, tools_module):
        """Extra kwargs should be ignored via **kwargs."""
        result = tools_module.execute_tool("check_habit", {
            "habit_name": "exercise",
            "unexpected_field": "should be ignored",
            "another_one": 42,
        })
        assert "Exercise" in result

    def test_unicode_habit_names(self, tools_module):
        """Should handle Unicode names correctly."""
        result = tools_module.execute_tool("add_habit", {"name": "瞑想する"})
        assert "瞑想する" in result

        result = tools_module.execute_tool("check_habit", {"habit_name": "瞑想"})
        assert "瞑想する" in result

    def test_very_long_habit_name(self, tools_module):
        """Should handle very long names."""
        long_name = "Read at least 30 pages of a technical book every single morning before work"
        result = tools_module.execute_tool("add_habit", {"name": long_name})
        assert long_name in result

    def test_empty_string_habit_name(self, tools_module):
        """Checking empty name should fail gracefully."""
        result = tools_module.execute_tool("check_habit", {"habit_name": ""})
        assert "couldn't find" in result.lower()

    def test_numeric_string_arguments(self, tools_module):
        """goal_number as string "1" instead of int 1."""
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A1"],
        })
        # Some models send numbers as strings
        result = tools_module.execute_tool("complete_action", {
            "goal_number": "1", "action_number": "1",
        })
        # May error or work depending on implementation
        # Should at minimum not crash
        assert isinstance(result, str)

    def test_null_arguments(self, tools_module):
        """Handle None/null values in arguments."""
        result = tools_module.execute_tool("write_journal", {
            "went_well": None,
            "mood": None,
        })
        assert "saved" in result.lower()

    def test_empty_array_arguments(self, tools_module):
        """Empty arrays should work."""
        result = tools_module.execute_tool("write_journal", {
            "went_well": [],
            "didnt_go_well": [],
        })
        assert "saved" in result.lower()

    def test_mood_out_of_range(self, tools_module):
        """Mood values outside 1-5 should be stored as-is (no validation crash)."""
        result = tools_module.execute_tool("write_journal", {"mood": 10})
        assert isinstance(result, str)
        # Should store it (tool doesn't validate range)
        today = tools_module._today()
        entry = tools_module._read_json(f"journal/{today}.json")
        assert entry["mood"] == 10


# ═══════════════════════════════════════════════════════════
# SCENARIO 9: Data Integrity Under Concurrent Operations
# ═══════════════════════════════════════════════════════════

class TestDataIntegrity:
    """Test data integrity when tools are called in rapid succession."""

    def test_rapid_habit_add_remove(self, tools_module):
        """Add and remove habits rapidly without corruption."""
        for i in range(10):
            tools_module.execute_tool("add_habit", {"name": f"Habit {i}"})

        habits = tools_module._read_json("habits.json")
        assert len(habits) == 10

        for i in range(0, 10, 2):
            tools_module.execute_tool("remove_habit", {"habit_name": f"Habit {i}"})

        habits = tools_module._read_json("habits.json")
        active = [h for h in habits if h.get("active", True)]
        assert len(active) == 5

    def test_check_uncheck_cycle(self, tools_module):
        """Rapid check/uncheck should leave correct final state."""
        tools_module.execute_tool("add_habit", {"name": "Toggle"})

        for _ in range(10):
            tools_module.execute_tool("check_habit", {"habit_name": "Toggle"})
            tools_module.execute_tool("uncheck_habit", {"habit_name": "Toggle"})
        tools_module.execute_tool("check_habit", {"habit_name": "Toggle"})

        result = tools_module.execute_tool("list_habits", {})
        assert "1/1" in result

    def test_multiple_journal_overwrites(self, tools_module):
        """Multiple journal writes in same day should merge cleanly."""
        tools_module.execute_tool("write_journal", {"went_well": ["Win 1"], "mood": 3})
        tools_module.execute_tool("write_journal", {"went_well": ["Win 2"], "mood": 4})
        tools_module.execute_tool("write_journal", {"learnings": ["Lesson 1"]})

        today = tools_module._today()
        entry = tools_module._read_json(f"journal/{today}.json")
        # Last explicit went_well wins
        assert entry["wentWell"] == ["Win 2"]
        # Mood from second write
        assert entry["mood"] == 4
        # Learnings from third write
        assert entry["learnings"] == ["Lesson 1"]

    def test_ow64_all_8_goals_all_64_actions(self, tools_module):
        """Fill all 8 goals with 8 actions each, then complete all."""
        tools_module.execute_tool("setup_goal", {"north_star": "Full OW64"})

        for g in range(1, 9):
            tools_module.execute_tool("setup_supporting_goal", {
                "goal_number": g,
                "title": f"Goal {g}",
                "actions": [f"Action {g}-{a}" for a in range(1, 9)],
            })

        ow64 = tools_module._read_json("ow64.json")
        assert len(ow64["supportingGoals"]) == 8
        for g in ow64["supportingGoals"]:
            assert len(g["actions"]) == 8
            assert all(a["text"] for a in g["actions"])

        # Complete all 64 actions
        for g in range(1, 9):
            for a in range(1, 9):
                result = tools_module.execute_tool("complete_action", {
                    "goal_number": g, "action_number": a,
                })
                assert "Completed" in result

        ow64 = tools_module._read_json("ow64.json")
        total_done = sum(
            1 for g in ow64["supportingGoals"]
            for a in g["actions"] if a["completed"]
        )
        assert total_done == 64

    def test_30_day_habit_log(self, tools_module):
        """Simulate 30 days of habit logging."""
        tools_module.execute_tool("add_habit", {"name": "Daily habit"})
        habits = tools_module._read_json("habits.json")
        habit_id = habits[0]["id"]

        log = {}
        for i in range(30):
            d = tools_module._days_ago(i)
            log[d] = {habit_id: True}
        tools_module._write_json("habit-log.json", log)

        tools_module.execute_tool("setup_goal", {"north_star": "Test"})
        result = tools_module.execute_tool("get_progress", {})
        assert "30" in result  # 30-day streak


# ═══════════════════════════════════════════════════════════
# SCENARIO 10: Full Pipeline Integration
# ═══════════════════════════════════════════════════════════

class TestFullPipeline:
    """Test the complete pipeline as wired in main.py."""

    def test_main_harada_flow_simulation(self, router, tools_module):
        """Simulate the full main.py handle_stop_and_process path for harada."""
        from persona_manager import PersonaManager
        from conversation import Conversation

        # Setup persona
        pm = PersonaManager()
        pm.switch("harada")
        persona = pm.get_current()
        assert persona["enable_tools"] is True

        # Create conversation
        conv = Conversation(persona_manager=pm, llm_router=router)
        transcript = "I finished my morning run and read for 30 minutes"
        conv.add_user_message(transcript)

        # Mock the API calls
        responses = [
            _make_tool_response([
                ("check_habit", {"habit_name": "morning run"}),
                ("check_habit", {"habit_name": "read"}),
            ]),
            _make_text_response("Great job! Morning run and reading are checked off. Keep the momentum going!"),
        ]

        # Setup habits first
        tools_module.execute_tool("setup_goal", {"north_star": "Be fit and well-read"})
        tools_module.execute_tool("add_habit", {"name": "Morning run"})
        tools_module.execute_tool("add_habit", {"name": "Read 30 min"})

        call_idx = [0]
        def mock_post(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return responses[idx] if idx < len(responses) else _make_text_response("(fallback)")

        with patch("llm_router.httpx.post", side_effect=mock_post):
            response = conv.get_response_with_tools(
                tools=tools_module.TOOL_DEFINITIONS,
                tool_executor=tools_module.execute_tool,
            )

        assert "morning run" in response.lower() or "great" in response.lower()
        conv.add_assistant_message(response)

        # Write overlay state
        from main import _write_overlay_state
        _write_overlay_state(transcript, response, conv)

        # Verify overlay
        state = json.loads(OVERLAY_FILE.read_text())
        assert state["dashboard"]["habitsCompleted"] == 2
        assert state["dashboard"]["habitsTotal"] == 2
        assert len(state["conversation"]) == 2

        OVERLAY_FILE.unlink(missing_ok=True)

    def test_main_non_harada_skips_tools(self, router):
        """Non-harada persona should use regular chat without tools."""
        from persona_manager import PersonaManager
        from conversation import Conversation

        pm = PersonaManager()
        pm.switch("assistant")
        persona = pm.get_current()
        assert not persona.get("enable_tools")

        conv = Conversation(persona_manager=pm, llm_router=router)
        conv.add_user_message("What's the weather?")

        # Should call regular chat, not chat_with_tools
        with patch("llm_router.httpx.post") as mock_post:
            mock_post.return_value = _make_text_response("I can't check the weather, but it's probably nice!")
            response = conv.get_response()

        assert isinstance(response, str)
        assert len(response) > 0

    def test_error_recovery_in_main_flow(self, router, tools_module):
        """Simulate the try/except in main.py's handle_stop_and_process."""
        from persona_manager import PersonaManager
        from conversation import Conversation
        import httpx

        pm = PersonaManager()
        pm.switch("harada")
        conv = Conversation(persona_manager=pm, llm_router=router)
        conv.add_user_message("check my habits")

        # Simulate 402 error
        with patch("llm_router.httpx.post", return_value=_make_error_response(402, "Quota exceeded")):
            try:
                response = conv.get_response_with_tools(
                    tools=tools_module.TOOL_DEFINITIONS,
                    tool_executor=tools_module.execute_tool,
                )
            except httpx.HTTPStatusError:
                response = "Sorry, I had trouble processing that. Check the logs for details."

        assert "sorry" in response.lower() or "trouble" in response.lower()

    def test_conversation_history_maintained_across_turns(self, router, tools_module):
        """Multi-turn conversation should maintain history."""
        from persona_manager import PersonaManager
        from conversation import Conversation

        pm = PersonaManager()
        pm.switch("harada")
        conv = Conversation(persona_manager=pm, llm_router=router)

        tools_module.execute_tool("setup_goal", {"north_star": "Test"})
        tools_module.execute_tool("add_habit", {"name": "Run"})

        # Turn 1
        conv.add_user_message("Check off my run")
        with patch("llm_router.httpx.post") as mock:
            captured_payloads = []
            def capture_post(*args, **kwargs):
                captured_payloads.append(kwargs.get("json", {}))
                if len(captured_payloads) == 1:
                    return _make_tool_response([("check_habit", {"habit_name": "run"})])
                return _make_text_response("Run checked!")
            mock.side_effect = capture_post

            r1 = conv.get_response_with_tools(
                tools=tools_module.TOOL_DEFINITIONS,
                tool_executor=tools_module.execute_tool,
            )
        conv.add_assistant_message(r1)
        assert len(conv.messages) == 2

        # Turn 2 — should include previous messages
        conv.add_user_message("How am I doing?")
        with patch("llm_router.httpx.post") as mock:
            captured_payloads = []
            def capture_post2(*args, **kwargs):
                captured_payloads.append(kwargs.get("json", {}))
                if len(captured_payloads) == 1:
                    return _make_tool_response([("get_progress", {})])
                return _make_text_response("Looking good!")
            mock.side_effect = capture_post2

            r2 = conv.get_response_with_tools(
                tools=tools_module.TOOL_DEFINITIONS,
                tool_executor=tools_module.execute_tool,
            )

        # Second call should have 3 messages (user, assistant, user)
        assert len(captured_payloads) >= 1
        msgs = captured_payloads[0]["messages"]
        # System + 3 conversation messages
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert len(user_msgs) == 2


# ═══════════════════════════════════════════════════════════
# SCENARIO 11: Tool Call Message Format Validation
# ═══════════════════════════════════════════════════════════

class TestToolCallMessageFormat:
    """Verify the messages sent back to the API after tool execution
    conform to the OpenAI format exactly."""

    def test_tool_result_messages_format(self, router, tools_module):
        """Tool results should include role='tool' and tool_call_id."""
        from harada_tools import TOOL_DEFINITIONS, execute_tool

        payloads = []
        call_count = [0]

        def capturing_post(*args, **kwargs):
            payload = kwargs.get("json", {})
            payloads.append(payload)
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([
                    ("list_habits", {}),
                    ("get_progress", {}),
                ])
            return _make_text_response("Done")

        with patch("llm_router.httpx.post", side_effect=capturing_post):
            router.chat_with_tools(
                llm_config={"provider": "redpill", "model": "test"},
                messages=[{"role": "user", "content": "test"}],
                system_prompt="test",
                tools=TOOL_DEFINITIONS,
                tool_executor=execute_tool,
            )

        # Second API call should have tool results
        assert len(payloads) >= 2
        second_msgs = payloads[1]["messages"]

        # Find tool result messages
        tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
        assert len(tool_msgs) == 2

        for tm in tool_msgs:
            assert "tool_call_id" in tm
            assert "content" in tm
            assert tm["role"] == "tool"
            assert isinstance(tm["content"], str)
            assert tm["tool_call_id"].startswith("call_")

    def test_assistant_tool_call_message_forwarded(self, router, tools_module):
        """The assistant message with tool_calls should be forwarded to the next API call."""
        from harada_tools import TOOL_DEFINITIONS, execute_tool

        payloads = []
        call_count = [0]

        def capturing_post(*args, **kwargs):
            payloads.append(kwargs.get("json", {}))
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_tool_response([("list_habits", {})])
            return _make_text_response("Done")

        with patch("llm_router.httpx.post", side_effect=capturing_post):
            router.chat_with_tools(
                llm_config={"provider": "redpill", "model": "test"},
                messages=[{"role": "user", "content": "test"}],
                system_prompt="test",
                tools=TOOL_DEFINITIONS,
                tool_executor=execute_tool,
            )

        # Second call should include: system, user, assistant(with tool_calls), tool(result)
        second_msgs = payloads[1]["messages"]
        roles = [m["role"] for m in second_msgs]
        assert roles == ["system", "user", "assistant", "tool"]

        # The assistant message should have tool_calls
        asst_msg = second_msgs[2]
        assert asst_msg["role"] == "assistant"
        assert "tool_calls" in asst_msg


# ═══════════════════════════════════════════════════════════
# SCENARIO 12: Streak Edge Cases
# ═══════════════════════════════════════════════════════════

class TestStreakEdgeCases:
    """Test streak calculation corner cases."""

    def test_streak_zero_no_habits(self, tools_module):
        """No habits means 0 streak."""
        tools_module.execute_tool("setup_goal", {"north_star": "X"})
        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["streak"] == 0

    def test_streak_zero_no_log(self, tools_module):
        """Habits exist but nothing logged."""
        tools_module.execute_tool("add_habit", {"name": "Test"})
        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["streak"] == 0

    def test_streak_one_day(self, tools_module):
        """All habits done today only."""
        tools_module.execute_tool("add_habit", {"name": "Test"})
        tools_module.execute_tool("check_habit", {"habit_name": "test"})
        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["streak"] == 1

    def test_streak_with_new_habit_added(self, tools_module):
        """Adding a new habit should break the streak if past days don't have it."""
        tools_module.execute_tool("add_habit", {"name": "Original"})
        habits = tools_module._read_json("habits.json")
        orig_id = habits[0]["id"]

        # 5 days of original habit
        log = {}
        for i in range(5):
            d = tools_module._days_ago(i)
            log[d] = {orig_id: True}
        tools_module._write_json("habit-log.json", log)

        # Now add new habit — past days don't have it
        tools_module.execute_tool("add_habit", {"name": "New habit"})

        state = tools_module.get_overlay_state([])
        # Streak should be 0 because the new habit isn't checked for any day
        assert state["dashboard"]["streak"] == 0

    def test_streak_partial_day_doesnt_count(self, tools_module):
        """Day with only some habits done doesn't count for streak."""
        tools_module.execute_tool("add_habit", {"name": "A"})
        tools_module.execute_tool("add_habit", {"name": "B"})
        habits = tools_module._read_json("habits.json")

        log = {
            tools_module._today(): {habits[0]["id"]: True, habits[1]["id"]: True},
            tools_module._days_ago(1): {habits[0]["id"]: True, habits[1]["id"]: False},  # partial
        }
        tools_module._write_json("habit-log.json", log)

        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["streak"] == 1  # only today counts


# ═══════════════════════════════════════════════════════════
# SCENARIO 13: OW64 Completion Percentage
# ═══════════════════════════════════════════════════════════

class TestOW64Completion:
    """Test OW64 completion percentage calculations."""

    @pytest.fixture(autouse=True)
    def setup_ow64(self, tools_module):
        tools_module.execute_tool("setup_goal", {"north_star": "Test"})

    def test_zero_completion(self, tools_module):
        """No goals set = 0%."""
        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["ow64Completion"] == 0

    def test_partial_completion(self, tools_module):
        """3/6 actions done = 50%."""
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1",
            "actions": ["A1", "A2", "A3", "A4", "A5", "A6"],
        })
        for a in [1, 2, 3]:
            tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": a})

        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["ow64Completion"] == 50
        assert state["dashboard"]["ow64Done"] == 3
        assert state["dashboard"]["ow64Total"] == 6

    def test_100_percent_completion(self, tools_module):
        """All actions done = 100%."""
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A1", "A2"],
        })
        tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})
        tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": 2})

        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["ow64Completion"] == 100

    def test_multiple_goals_mixed_completion(self, tools_module):
        """Multiple goals with different completion rates."""
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A", "B"],
        })
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 2, "title": "G2", "actions": ["C", "D", "E", "F"],
        })
        # Complete 1/2 of G1, 2/4 of G2
        tools_module.execute_tool("complete_action", {"goal_number": 1, "action_number": 1})
        tools_module.execute_tool("complete_action", {"goal_number": 2, "action_number": 1})
        tools_module.execute_tool("complete_action", {"goal_number": 2, "action_number": 2})

        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["ow64Done"] == 3
        assert state["dashboard"]["ow64Total"] == 6
        assert state["dashboard"]["ow64Completion"] == 50

        # Per-goal progress
        gp = state["dashboard"]["goalProgress"]
        g1 = next(g for g in gp if g["title"] == "G1")
        g2 = next(g for g in gp if g["title"] == "G2")
        assert g1["pct"] == 50
        assert g2["pct"] == 50

    def test_empty_actions_not_counted(self, tools_module):
        """Empty action slots should not count toward total."""
        tools_module.execute_tool("setup_supporting_goal", {
            "goal_number": 1, "title": "G1", "actions": ["A1", "A2"],
        })
        # Goal has 8 action slots but only 2 have text
        state = tools_module.get_overlay_state([])
        assert state["dashboard"]["ow64Total"] == 2


# ═══════════════════════════════════════════════════════════
# SCENARIO 14: Concurrent Model Routing
# ═══════════════════════════════════════════════════════════

class TestModelRouting:
    """Test that model override correctly routes to different models."""

    def test_model_override_applies_to_tool_calls(self, router):
        """Model override should be used in API calls."""
        from persona_manager import PersonaManager
        from conversation import Conversation

        pm = PersonaManager()
        pm.switch("harada")
        conv = Conversation(persona_manager=pm, llm_router=router)
        conv.add_user_message("hello")

        captured_models = []
        def capturing_post(*args, **kwargs):
            model = kwargs.get("json", {}).get("model", "?")
            captured_models.append(model)
            return _make_text_response("Hi!")

        with patch("llm_router.httpx.post", side_effect=capturing_post):
            with patch("conversation.ModelManager") as MockMM:
                MockMM.return_value.get_current_model.return_value = "deepseek/deepseek-v3.2"
                result = conv.get_response_with_tools(
                    tools=[], tool_executor=lambda n, a: "",
                )

        assert captured_models[0] == "deepseek/deepseek-v3.2"

    def test_default_model_used_without_override(self, router):
        """Without override, persona's default model should be used."""
        from persona_manager import PersonaManager
        from conversation import Conversation

        pm = PersonaManager()
        pm.switch("harada")
        conv = Conversation(persona_manager=pm, llm_router=router)
        conv.add_user_message("hello")

        captured_models = []
        def capturing_post(*args, **kwargs):
            model = kwargs.get("json", {}).get("model", "?")
            captured_models.append(model)
            return _make_text_response("Hi!")

        with patch("llm_router.httpx.post", side_effect=capturing_post):
            with patch("conversation.ModelManager") as MockMM:
                MockMM.return_value.get_current_model.return_value = None
                result = conv.get_response_with_tools(
                    tools=[], tool_executor=lambda n, a: "",
                )

        # Harada persona defaults to z-ai/glm-5
        assert captured_models[0] == "z-ai/glm-5"
