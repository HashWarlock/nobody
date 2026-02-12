import { StringEnum } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { calcAvg30d, calcProgressSnapshot, dateRange, daysAgo, today } from "../data/analytics.js";
import type { HaradaStore } from "../data/store.js";
import type { JournalEntry } from "../data/types.js";

const ProgressParams = Type.Object({
  action: StringEnum(["snapshot", "trends", "insights", "report"] as const),
  days: Type.Optional(Type.Number({ description: "Number of days for trends (default 30)" })),
});

export function registerProgressTool(pi: ExtensionAPI, getStore: () => HaradaStore): void {
  pi.registerTool({
    name: "harada_progress",
    label: "Harada Progress",
    description:
      "Query progress analytics. Actions: snapshot (full overview), trends (mood/energy/completion over time), insights (coaching observations), report (complete markdown report).",
    parameters: ProgressParams,

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const store = getStore();
      const data = store.getAllData();

      if (!data.goalForm) {
        return { content: [{ type: "text", text: "No Harada data. Set up a goal form first." }], details: { error: true } };
      }

      switch (params.action) {
        case "snapshot": {
          const s = calcProgressSnapshot(data);
          const lines = [
            "📊 HARADA PROGRESS SNAPSHOT",
            "",
            `⭐ North Star: ${data.goalForm.northStar}`,
            `📅 Day ${s.daysSinceStart} | ${s.daysToDeadline > 0 ? `${s.daysToDeadline} days remaining` : "No deadline"}`,
            "",
            `📈 OW64 Completion: ${s.totalActionsCompleted}/${s.totalActions} (${s.ow64Completion}%)`,
          ];
          for (const g of s.goalCompletion) {
            if (g.title) {
              const bar = progressBar(g.pct, 15);
              lines.push(`  ${g.goalId}. ${g.title}: ${bar} ${g.pct}% [${g.completed}/${g.total}]`);
            }
          }
          lines.push("");
          lines.push(`✅ Today's Habits: ${s.todayHabitsCompleted}/${s.todayHabitsTotal}`);
          lines.push(`🔥 Habit Streak: ${s.habitStreak} days (best: ${s.longestStreak})`);
          lines.push(`📊 30-Day Habit Rate: ${s.habitCompletionRate30d}%`);
          lines.push(`📓 Journal Streak: ${s.journalStreak} days (${s.journalTotal} total)`);
          if (s.avgMood30d !== null) lines.push(`😊 30-Day Avg Mood: ${s.avgMood30d}/5`);
          if (s.avgEnergy30d !== null) lines.push(`⚡ 30-Day Avg Energy: ${s.avgEnergy30d}/5`);

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "snapshot", snapshot: s },
          };
        }

        case "trends": {
          const numDays = params.days ?? 30;
          const dates = dateRange(daysAgo(numDays - 1), today());
          const activeHabits = data.habits.filter(h => h.active);

          const lines = [`📈 Trends (last ${numDays} days)`, ""];

          // Habit completion trend (weekly buckets)
          lines.push("Habit Completion by Week:");
          const weekBuckets: { week: string; rate: number }[] = [];
          for (let i = 0; i < dates.length; i += 7) {
            const weekDates = dates.slice(i, i + 7);
            let done = 0, total = 0;
            for (const d of weekDates) {
              for (const h of activeHabits) {
                total++;
                if (data.habitLog[d]?.[h.id] === true) done++;
              }
            }
            const rate = total > 0 ? Math.round((done / total) * 100) : 0;
            weekBuckets.push({ week: `${weekDates[0]} → ${weekDates[weekDates.length - 1]}`, rate });
            lines.push(`  ${weekBuckets[weekBuckets.length - 1]!.week}: ${progressBar(rate, 20)} ${rate}%`);
          }

          // Mood/Energy trend
          lines.push("");
          lines.push("Mood & Energy Trend:");
          const journals = data.journals;
          for (let i = 0; i < dates.length; i += 7) {
            const weekDates = dates.slice(i, i + 7);
            const moods = weekDates.map(d => journals[d]?.mood).filter((m): m is number => m !== undefined);
            const energies = weekDates.map(d => journals[d]?.energy).filter((e): e is number => e !== undefined);
            const avgMood = moods.length > 0 ? (moods.reduce((a, b) => a + b, 0) / moods.length).toFixed(1) : "—";
            const avgEnergy = energies.length > 0 ? (energies.reduce((a, b) => a + b, 0) / energies.length).toFixed(1) : "—";
            lines.push(`  ${weekDates[0]}: Mood ${avgMood}/5 | Energy ${avgEnergy}/5`);
          }

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "trends", weekBuckets },
          };
        }

        case "insights": {
          const s = calcProgressSnapshot(data);
          const insights: string[] = [];

          // Pace analysis
          if (s.daysToDeadline > 0 && s.totalActions > 0) {
            const remaining = s.totalActions - s.totalActionsCompleted;
            const pace = remaining / s.daysToDeadline;
            if (pace > 1) {
              insights.push(`⚠️ You need to complete ~${pace.toFixed(1)} actions/day to hit your deadline. Consider prioritizing or extending.`);
            } else if (pace < 0.2) {
              insights.push(`🚀 You're well ahead of pace! Consider raising the bar or pulling the deadline forward.`);
            } else {
              insights.push(`👍 You're on a solid pace. Keep the momentum going.`);
            }
          }

          // Habit consistency
          if (s.habitCompletionRate30d < 50) {
            insights.push(`📉 Habit completion at ${s.habitCompletionRate30d}%. Consider reducing habits to 3-5 most impactful ones.`);
          } else if (s.habitCompletionRate30d > 85) {
            insights.push(`🌟 ${s.habitCompletionRate30d}% habit rate — exceptional consistency! Your systems are working.`);
          }

          // Streak
          if (s.habitStreak === 0) {
            insights.push(`💪 No active streak. Today is day 1. Start now.`);
          } else if (s.habitStreak >= 21) {
            insights.push(`🏆 ${s.habitStreak}-day streak! This is becoming automatic. You're building identity, not just habits.`);
          }

          // Journal
          if (s.journalStreak === 0) {
            insights.push(`📝 Write tonight's journal. Reflection compounds awareness.`);
          }

          // Weakest goal
          const weakest = s.goalCompletion.filter(g => g.title).sort((a, b) => a.pct - b.pct)[0];
          if (weakest && weakest.pct < 25) {
            insights.push(`🎯 "${weakest.title}" is your weakest area at ${weakest.pct}%. Focus energy here this week.`);
          }

          // Mood
          const avgMood = calcAvg30d(data.journals, "mood");
          if (avgMood !== null && avgMood < 3) {
            insights.push(`💛 Average mood is ${avgMood}/5. Are you pushing too hard? Sustainable progress requires recovery.`);
          }

          if (insights.length === 0) {
            insights.push("✨ Things look balanced. Keep going and trust the process.");
          }

          return {
            content: [{ type: "text", text: `💡 COACHING INSIGHTS\n\n${insights.join("\n\n")}` }],
            details: { action: "insights", insights },
          };
        }

        case "report": {
          const s = calcProgressSnapshot(data);
          const lines = [
            "# Harada Method — Progress Report",
            `> Generated ${new Date().toISOString().split("T")[0]}`,
            "",
            `## ⭐ North Star`,
            data.goalForm.northStar,
            "",
            `**Day ${s.daysSinceStart}** | ${s.daysToDeadline > 0 ? `**${s.daysToDeadline} days remaining**` : "No deadline"}`,
            "",
            `## 📊 OW64 Progress: ${s.ow64Completion}%`,
            "",
          ];

          for (const g of s.goalCompletion) {
            if (!g.title) continue;
            lines.push(`### Goal ${g.goalId}: ${g.title} — ${g.pct}%`);
            const goal = data.ow64?.supportingGoals.find(sg => sg.id === g.goalId);
            if (goal) {
              for (const a of goal.actions) {
                if (!a.text) continue;
                lines.push(`- [${a.completed ? "x" : " "}] ${a.text}${a.isHabit ? " 🔄" : ""}`);
              }
            }
            lines.push("");
          }

          lines.push(`## ✅ Habits`, "");
          lines.push(`- Current Streak: **${s.habitStreak} days**`);
          lines.push(`- Longest Streak: **${s.longestStreak} days**`);
          lines.push(`- 30-Day Rate: **${s.habitCompletionRate30d}%**`);
          lines.push("");

          lines.push(`## 📓 Journal`, "");
          lines.push(`- Streak: **${s.journalStreak} days**`);
          lines.push(`- Total Entries: **${s.journalTotal}**`);
          if (s.avgMood30d !== null) lines.push(`- 30-Day Avg Mood: **${s.avgMood30d}/5**`);
          if (s.avgEnergy30d !== null) lines.push(`- 30-Day Avg Energy: **${s.avgEnergy30d}/5**`);
          lines.push("");

          lines.push(`## 💫 Affirmation`, "", `> ${data.goalForm.affirmation || "_Not set_"}`);

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "report", snapshot: s },
          };
        }

        default:
          return { content: [{ type: "text", text: `Unknown action: ${params.action}` }], details: { error: true } };
      }
    },

    renderCall(args, theme) {
      return new Text(theme.fg("toolTitle", theme.bold("harada_progress ")) + theme.fg("muted", args.action), 0, 0);
    },

    renderResult(result, _options, theme) {
      const text = result.content[0];
      const content = text?.type === "text" ? text.text : "";
      if (result.details?.error) return new Text(theme.fg("error", content), 0, 0);
      return new Text(theme.fg("success", "✓ ") + theme.fg("muted", content.split("\n")[0] ?? ""), 0, 0);
    },
  });
}

function progressBar(pct: number, width: number): string {
  const filled = Math.round((pct / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}
