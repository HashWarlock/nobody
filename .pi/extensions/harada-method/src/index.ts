/**
 * Harada Method Extension for pi
 *
 * A complete goal-achievement system implementing the Harada Method:
 * - Long-term Goal Form (North Star definition)
 * - Open Window 64 chart (goal decomposition)
 * - Daily Habit Tracking with streaks
 * - Daily Journal / Reflection
 * - Visual Dashboard Overlay
 * - Coaching nudges and context injection
 *
 * Commands:
 *   /harada       — Open the dashboard overlay (also Ctrl+H)
 *   /ow64         — Open OW64 mandala grid overlay
 *   /habits       — Open habit tracker overlay
 *   /harada-setup — Guided first-time setup
 *   /harada-export— Export all data to markdown
 *
 * Tools (LLM callable):
 *   harada_goal_form  — Manage long-term goal form
 *   harada_ow64       — Manage Open Window 64 chart
 *   harada_habits     — Track daily habits
 *   harada_journal    — Daily reflection entries
 *   harada_progress   — Query progress analytics
 */

import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Key } from "@mariozechner/pi-tui";

import { calcProgressSnapshot, calcTodayHabits, today } from "./data/analytics.js";
import { HaradaStore } from "./data/store.js";
import type { HaradaData } from "./data/types.js";
import { registerGoalFormTool } from "./tools/goal-form.js";
import { registerOW64Tool } from "./tools/ow64.js";
import { registerHabitsTool } from "./tools/habits.js";
import { registerJournalTool } from "./tools/journal.js";
import { registerProgressTool } from "./tools/progress.js";
import { showDashboard } from "./ui/dashboard.js";
import { showHabitTracker } from "./ui/habit-tracker.js";
import { showOW64Grid } from "./ui/ow64-grid.js";

export default function haradaMethodExtension(pi: ExtensionAPI): void {
  let store: HaradaStore;

  // ── Initialize store on session events ──────────────────

  function initStore(ctx: ExtensionContext): void {
    store = new HaradaStore(ctx.cwd);
  }

  function getData(): HaradaData {
    return store.getAllData();
  }

  // ── Widget & Status Updates ─────────────────────────────

  function updateWidgetAndStatus(ctx: ExtensionContext): void {
    const data = getData();
    const snapshot = calcProgressSnapshot(data);

    // Status line in footer
    if (data.goalForm) {
      const todayH = calcTodayHabits(data.habits, data.habitLog);
      const statusText = todayH.total > 0
        ? `📋 ${todayH.completed}/${todayH.total} habits`
        : "📋 harada";
      ctx.ui.setStatus("harada", ctx.ui.theme.fg("accent", statusText));
    } else {
      ctx.ui.setStatus("harada", ctx.ui.theme.fg("dim", "📋 /harada-setup to begin"));
    }

    // Persistent widget above editor
    if (data.goalForm) {
      const th = ctx.ui.theme;
      const streak = snapshot.habitStreak > 0 ? `🔥 ${snapshot.habitStreak}d` : "";
      const habitsStr = snapshot.todayHabitsTotal > 0
        ? `✅ ${snapshot.todayHabitsCompleted}/${snapshot.todayHabitsTotal}`
        : "";
      const ow64Str = snapshot.totalActions > 0 ? `${snapshot.ow64Completion}% OW64` : "";
      const daysStr = snapshot.daysToDeadline > 0
        ? `Day ${snapshot.daysSinceStart}/${snapshot.daysSinceStart + snapshot.daysToDeadline}`
        : "";

      const parts = [daysStr, habitsStr, streak, ow64Str].filter(Boolean);
      const line = th.fg("accent", "🎯 ") + th.fg("muted", parts.join(" │ "));
      ctx.ui.setWidget("harada-progress", [line]);
    } else {
      ctx.ui.setWidget("harada-progress", undefined);
    }
  }

  // ── Session Events ──────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    initStore(ctx);
    updateWidgetAndStatus(ctx);

    // Show coaching nudge if goal exists
    const data = getData();
    if (data.goalForm) {
      const snapshot = calcProgressSnapshot(data);
      const th = ctx.ui.theme;

      // Show affirmation at session start
      let nudge = th.fg("accent", "💫 ") + th.fg("muted", th.italic(data.goalForm.affirmation));

      // Streak milestone celebrations
      if (snapshot.habitStreak > 0 && snapshot.habitStreak % 7 === 0) {
        nudge += "\n" + th.fg("success", `🏆 ${snapshot.habitStreak}-day streak! Keep going!`);
      }

      // Gentle habit reminder
      const todayH = calcTodayHabits(data.habits, data.habitLog);
      if (todayH.total > 0 && todayH.completed < todayH.total) {
        const remaining = todayH.total - todayH.completed;
        nudge += "\n" + th.fg("dim", `📋 ${remaining} habit${remaining > 1 ? "s" : ""} remaining today`);
      }

      ctx.ui.notify(nudge, "info");
    }
  });

  pi.on("session_switch", async (_event, ctx) => { initStore(ctx); updateWidgetAndStatus(ctx); });
  pi.on("session_fork", async (_event, ctx) => { initStore(ctx); updateWidgetAndStatus(ctx); });
  pi.on("session_tree", async (_event, ctx) => { initStore(ctx); updateWidgetAndStatus(ctx); });

  // Refresh widget after tool calls that modify harada data
  pi.on("tool_result", async (event, ctx) => {
    if (event.toolName?.startsWith("harada_")) {
      updateWidgetAndStatus(ctx);
    }
  });

  // ── Context Injection ───────────────────────────────────

  pi.on("before_agent_start", async (_event, _ctx) => {
    const data = getData();
    if (!data.goalForm) return;

    const snapshot = calcProgressSnapshot(data);
    const todayStr = today();
    const todayJournal = data.journals[todayStr];

    let context = `[HARADA METHOD CONTEXT]
North Star: ${data.goalForm.northStar}
Day ${snapshot.daysSinceStart} of journey | ${snapshot.daysToDeadline > 0 ? `${snapshot.daysToDeadline} days to deadline` : "No deadline set"}
OW64 Progress: ${snapshot.totalActionsCompleted}/${snapshot.totalActions} actions (${snapshot.ow64Completion}%)
Today's Habits: ${snapshot.todayHabitsCompleted}/${snapshot.todayHabitsTotal} completed
Habit Streak: ${snapshot.habitStreak} days (best: ${snapshot.longestStreak})
30-Day Habit Rate: ${snapshot.habitCompletionRate30d}%`;

    if (!todayJournal) {
      context += "\n⚠️ No journal entry for today yet.";
    }

    return {
      message: {
        customType: "harada-context",
        content: context,
        display: false,
      },
    };
  });

  // ── Register Tools ──────────────────────────────────────

  registerGoalFormTool(pi, () => store);
  registerOW64Tool(pi, () => store);
  registerHabitsTool(pi, () => store);
  registerJournalTool(pi, () => store);
  registerProgressTool(pi, () => store);

  // ── Register Commands ───────────────────────────────────

  pi.registerCommand("harada", {
    description: "Open Harada Method dashboard overlay",
    handler: async (_args, ctx) => {
      if (!ctx.hasUI) { ctx.ui.notify("/harada requires interactive mode", "error"); return; }
      const data = getData();
      if (!data.goalForm) {
        ctx.ui.notify("No goal set up yet. Use /harada-setup or ask me to help you set up your Harada goal.", "warning");
        return;
      }
      await showDashboard(ctx, data);
      updateWidgetAndStatus(ctx);
    },
  });

  pi.registerCommand("ow64", {
    description: "Open OW64 mandala grid overlay",
    handler: async (_args, ctx) => {
      if (!ctx.hasUI) { ctx.ui.notify("/ow64 requires interactive mode", "error"); return; }
      const data = getData();
      if (!data.ow64) {
        ctx.ui.notify("No OW64 chart set up yet. Ask me to help decompose your goal.", "warning");
        return;
      }
      await showOW64Grid(ctx, data);
    },
  });

  pi.registerCommand("habits", {
    description: "Open habit tracker overlay",
    handler: async (_args, ctx) => {
      if (!ctx.hasUI) { ctx.ui.notify("/habits requires interactive mode", "error"); return; }
      const data = getData();
      if (data.habits.filter(h => h.active).length === 0) {
        ctx.ui.notify("No active habits. Ask me to help set up your daily habits from OW64 actions.", "warning");
        return;
      }
      await showHabitTracker(ctx, data, store);
      updateWidgetAndStatus(ctx);
    },
  });

  pi.registerCommand("harada-setup", {
    description: "Start guided Harada Method setup",
    handler: async (_args, ctx) => {
      ctx.ui.setEditorText("/skill:harada-coach Help me set up my Harada Method goal form from scratch. Guide me through each question one at a time, starting with discovering my north star goal.");
      ctx.ui.notify("Press Enter to begin the guided setup with the Harada coach.", "info");
    },
  });

  pi.registerCommand("harada-export", {
    description: "Export all Harada data to markdown",
    handler: async (_args, ctx) => {
      const data = getData();
      if (!data.goalForm) {
        ctx.ui.notify("No Harada data to export.", "warning");
        return;
      }
      pi.sendUserMessage("Use the harada_progress tool with action 'report' to generate a complete markdown export of all my Harada data, then write it to .pi/harada/export.md");
    },
  });

  // ── Keyboard Shortcut ───────────────────────────────────

  pi.registerShortcut(Key.ctrl("h"), {
    description: "Open Harada dashboard",
    handler: async (ctx) => {
      const data = getData();
      if (!data.goalForm) {
        ctx.ui.notify("No goal set up. Use /harada-setup", "warning");
        return;
      }
      await showDashboard(ctx, data);
      updateWidgetAndStatus(ctx);
    },
  });
}
