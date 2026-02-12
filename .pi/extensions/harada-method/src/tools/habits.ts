import { StringEnum } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { calcHabitStreak, calcTodayHabits, dateRange, daysAgo, today } from "../data/analytics.js";
import type { HaradaStore } from "../data/store.js";

const HabitsParams = Type.Object({
  action: StringEnum(["list", "check", "uncheck", "add", "remove", "history"] as const),
  habitId: Type.Optional(Type.String({ description: "Habit ID to check/uncheck/remove" })),
  name: Type.Optional(Type.String({ description: "Name for new habit (for add)" })),
  frequency: Type.Optional(StringEnum(["daily", "weekday", "weekly"] as const)),
  date: Type.Optional(Type.String({ description: "Date (YYYY-MM-DD), defaults to today" })),
  days: Type.Optional(Type.Number({ description: "Number of days for history (default 7)" })),
});

export function registerHabitsTool(pi: ExtensionAPI, getStore: () => HaradaStore): void {
  pi.registerTool({
    name: "harada_habits",
    label: "Harada Habits",
    description:
      "Track daily habits. Actions: list (today's habits with status), check (mark habit done), uncheck (undo), add (new habit), remove (deactivate), history (completion history for N days).",
    parameters: HabitsParams,

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const store = getStore();
      const todayStr = params.date ?? today();

      switch (params.action) {
        case "list": {
          const habits = store.getHabits().filter(h => h.active);
          const log = store.getHabitLog();
          const dayLog = log[todayStr] ?? {};
          const streaks = calcHabitStreak(habits, log);
          const todayH = calcTodayHabits(habits, log);

          if (habits.length === 0) {
            return { content: [{ type: "text", text: "No active habits. Use 'add' or promote actions from OW64." }], details: { habits: [], todayLog: {} } };
          }

          const lines = [`📋 Habits for ${todayStr} (${todayH.completed}/${todayH.total})`, ""];
          for (const h of habits) {
            const done = dayLog[h.id] === true;
            const mark = done ? "✅" : "☐";
            const freq = h.frequency !== "daily" ? ` (${h.frequency})` : "";
            lines.push(`  ${mark} [${h.id}] ${h.name}${freq}`);
          }
          lines.push("");
          lines.push(`🔥 Streak: ${streaks.current} days | Best: ${streaks.longest} days`);

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "list", habits, todayLog: dayLog, streaks },
          };
        }

        case "check": {
          if (!params.habitId) return { content: [{ type: "text", text: "habitId required" }], details: { error: true } };
          const habits = store.getHabits();
          const habit = habits.find(h => h.id === params.habitId);
          if (!habit) return { content: [{ type: "text", text: `Habit '${params.habitId}' not found` }], details: { error: true } };

          const log = store.getHabitLog();
          if (!log[todayStr]) log[todayStr] = {};
          log[todayStr]![params.habitId] = true;
          store.saveHabitLog(log);

          const todayH = calcTodayHabits(habits.filter(h => h.active), log);
          const allDone = todayH.completed === todayH.total;

          return {
            content: [{ type: "text", text: `✅ ${habit.name} — done!${allDone ? " 🎉 All habits complete for today!" : ` (${todayH.completed}/${todayH.total})`}` }],
            details: { action: "check", habitId: params.habitId, todayCompleted: todayH.completed, todayTotal: todayH.total },
          };
        }

        case "uncheck": {
          if (!params.habitId) return { content: [{ type: "text", text: "habitId required" }], details: { error: true } };
          const log = store.getHabitLog();
          if (log[todayStr]) {
            log[todayStr]![params.habitId] = false;
            store.saveHabitLog(log);
          }
          return {
            content: [{ type: "text", text: `↩️ Unchecked: ${params.habitId}` }],
            details: { action: "uncheck", habitId: params.habitId },
          };
        }

        case "add": {
          if (!params.name) return { content: [{ type: "text", text: "name required" }], details: { error: true } };
          const habits = store.getHabits();
          const id = `habit-custom-${Date.now()}`;
          habits.push({
            id,
            name: params.name,
            frequency: params.frequency ?? "daily",
            active: true,
            createdAt: new Date().toISOString(),
          });
          store.saveHabits(habits);
          return {
            content: [{ type: "text", text: `✅ Added habit: ${params.name} (${params.frequency ?? "daily"}) [${id}]` }],
            details: { action: "add", habitId: id },
          };
        }

        case "remove": {
          if (!params.habitId) return { content: [{ type: "text", text: "habitId required" }], details: { error: true } };
          const habits = store.getHabits();
          const habit = habits.find(h => h.id === params.habitId);
          if (!habit) return { content: [{ type: "text", text: "Habit not found" }], details: { error: true } };
          habit.active = false;
          store.saveHabits(habits);
          return {
            content: [{ type: "text", text: `🗑️ Deactivated: ${habit.name}` }],
            details: { action: "remove", habitId: params.habitId },
          };
        }

        case "history": {
          const habits = store.getHabits().filter(h => h.active);
          const log = store.getHabitLog();
          const numDays = params.days ?? 7;
          const dates = dateRange(daysAgo(numDays - 1), today());

          if (habits.length === 0) {
            return { content: [{ type: "text", text: "No active habits." }], details: { action: "history" } };
          }

          const lines = [`📊 Habit History (last ${numDays} days)`, ""];
          // Header
          const nameWidth = 20;
          let header = "Habit".padEnd(nameWidth);
          for (const d of dates) {
            header += d.slice(5, 10).padStart(6); // MM-DD
          }
          lines.push(header);
          lines.push("─".repeat(header.length));

          for (const h of habits) {
            let row = h.name.slice(0, nameWidth - 1).padEnd(nameWidth);
            for (const d of dates) {
              const done = log[d]?.[h.id] === true;
              row += (done ? "  ✅ " : "  ☐  ").padStart(6);
            }
            lines.push(row);
          }

          // Daily rates
          lines.push("─".repeat(header.length));
          let rateRow = "Daily Rate %".padEnd(nameWidth);
          for (const d of dates) {
            const dayLog = log[d] ?? {};
            const done = habits.filter(h => dayLog[h.id] === true).length;
            const rate = habits.length > 0 ? Math.round((done / habits.length) * 100) : 0;
            rateRow += `${rate}%`.padStart(6);
          }
          lines.push(rateRow);

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "history", numDays },
          };
        }

        default:
          return { content: [{ type: "text", text: `Unknown action: ${params.action}` }], details: { error: true } };
      }
    },

    renderCall(args, theme) {
      let text = theme.fg("toolTitle", theme.bold("harada_habits ")) + theme.fg("muted", args.action);
      if (args.habitId) text += " " + theme.fg("accent", args.habitId);
      return new Text(text, 0, 0);
    },

    renderResult(result, _options, theme) {
      const text = result.content[0];
      const content = text?.type === "text" ? text.text : "";
      if (result.details?.error) return new Text(theme.fg("error", content), 0, 0);
      return new Text(theme.fg("success", "✓ ") + theme.fg("muted", content.split("\n")[0] ?? ""), 0, 0);
    },
  });
}
