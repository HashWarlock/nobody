import { StringEnum } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import type { HaradaStore } from "../data/store.js";
import type { ActionItem, OW64Chart, SupportingGoal } from "../data/types.js";

const OW64Params = Type.Object({
  action: StringEnum(["setup", "view", "set_goal", "set_action", "complete", "uncomplete", "promote_habit", "export"] as const),
  goalId: Type.Optional(Type.Number({ description: "Supporting goal ID (1-8)" })),
  goalTitle: Type.Optional(Type.String({ description: "Title for a supporting goal" })),
  actionIndex: Type.Optional(Type.Number({ description: "Action index within goal (1-8)" })),
  actionText: Type.Optional(Type.String({ description: "Action item text" })),
  northStar: Type.Optional(Type.String({ description: "North star goal (for setup)" })),
  goals: Type.Optional(Type.Array(
    Type.Object({
      id: Type.Number(),
      title: Type.String(),
      actions: Type.Array(Type.String()),
    }),
    { description: "Full goals with actions for bulk setup" }
  )),
});

export function registerOW64Tool(pi: ExtensionAPI, getStore: () => HaradaStore): void {
  pi.registerTool({
    name: "harada_ow64",
    label: "Harada OW64",
    description:
      "Manage the Open Window 64 chart. Actions: setup (create with all goals/actions), view (show chart), set_goal (set goal title), set_action (set action text), complete (mark action done), uncomplete (undo), promote_habit (flag action as daily habit), export (markdown).",
    parameters: OW64Params,

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const store = getStore();

      switch (params.action) {
        case "setup": {
          const goalForm = store.getGoalForm();
          const ns = params.northStar ?? goalForm?.northStar ?? "";
          if (!ns) {
            return { content: [{ type: "text", text: "Error: northStar required. Set up a goal form first or provide northStar." }], details: { error: true } };
          }

          const supportingGoals: SupportingGoal[] = [];
          if (params.goals && params.goals.length > 0) {
            for (const g of params.goals) {
              const actions: ActionItem[] = g.actions.map((text: string, i: number) => ({
                id: `${g.id}-${i + 1}`,
                goalId: g.id,
                text,
                completed: false,
                isHabit: false,
              }));
              // Pad to 8 actions
              while (actions.length < 8) {
                actions.push({
                  id: `${g.id}-${actions.length + 1}`,
                  goalId: g.id,
                  text: "",
                  completed: false,
                  isHabit: false,
                });
              }
              supportingGoals.push({ id: g.id, title: g.title, actions: actions.slice(0, 8) });
            }
          }
          // Pad to 8 goals
          while (supportingGoals.length < 8) {
            const gid = supportingGoals.length + 1;
            supportingGoals.push({
              id: gid,
              title: "",
              actions: Array.from({ length: 8 }, (_, i) => ({
                id: `${gid}-${i + 1}`,
                goalId: gid,
                text: "",
                completed: false,
                isHabit: false,
              })),
            });
          }

          const chart: OW64Chart = { northStar: ns, supportingGoals: supportingGoals.slice(0, 8) };
          store.saveOW64(chart);

          const filled = chart.supportingGoals.filter(g => g.title).length;
          const actionsFilled = chart.supportingGoals.reduce((s, g) => s + g.actions.filter(a => a.text).length, 0);
          return {
            content: [{ type: "text", text: `✅ OW64 chart created! ${filled}/8 goals, ${actionsFilled}/64 actions defined.` }],
            details: { action: "setup", chart },
          };
        }

        case "view": {
          const chart = store.getOW64();
          if (!chart) {
            return { content: [{ type: "text", text: "No OW64 chart. Use 'setup' first." }], details: { action: "view", chart: null } };
          }
          const lines = [`⭐ ${chart.northStar}`, ""];
          for (const g of chart.supportingGoals) {
            if (!g.title) continue;
            const done = g.actions.filter(a => a.completed).length;
            lines.push(`[Goal ${g.id}] ${g.title} (${done}/8)`);
            for (const a of g.actions) {
              if (!a.text) continue;
              const mark = a.completed ? "✅" : "☐";
              const habit = a.isHabit ? " 🔄" : "";
              lines.push(`  ${mark} ${a.id}: ${a.text}${habit}`);
            }
            lines.push("");
          }
          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "view", chart },
          };
        }

        case "set_goal": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart. Use 'setup' first." }], details: { error: true } };
          if (!params.goalId || params.goalId < 1 || params.goalId > 8) {
            return { content: [{ type: "text", text: "goalId must be 1-8" }], details: { error: true } };
          }
          const goal = chart.supportingGoals.find(g => g.id === params.goalId);
          if (goal && params.goalTitle) {
            goal.title = params.goalTitle;
            store.saveOW64(chart);
            return { content: [{ type: "text", text: `✅ Goal ${params.goalId}: "${params.goalTitle}"` }], details: { action: "set_goal", chart } };
          }
          return { content: [{ type: "text", text: "goalTitle required" }], details: { error: true } };
        }

        case "set_action": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart." }], details: { error: true } };
          if (!params.goalId || !params.actionIndex) {
            return { content: [{ type: "text", text: "goalId and actionIndex required" }], details: { error: true } };
          }
          const goal = chart.supportingGoals.find(g => g.id === params.goalId);
          if (!goal) return { content: [{ type: "text", text: `Goal ${params.goalId} not found` }], details: { error: true } };
          const action = goal.actions[params.actionIndex - 1];
          if (!action) return { content: [{ type: "text", text: `Action index must be 1-8` }], details: { error: true } };
          if (params.actionText) action.text = params.actionText;
          store.saveOW64(chart);
          return { content: [{ type: "text", text: `✅ Action ${action.id}: "${action.text}"` }], details: { action: "set_action", chart } };
        }

        case "complete": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart." }], details: { error: true } };
          if (!params.goalId || !params.actionIndex) {
            return { content: [{ type: "text", text: "goalId and actionIndex required" }], details: { error: true } };
          }
          const goal = chart.supportingGoals.find(g => g.id === params.goalId);
          const action = goal?.actions[params.actionIndex - 1];
          if (!action) return { content: [{ type: "text", text: "Action not found" }], details: { error: true } };
          action.completed = true;
          action.completedAt = new Date().toISOString();
          store.saveOW64(chart);
          return { content: [{ type: "text", text: `✅ Completed: ${action.id} — ${action.text}` }], details: { action: "complete", chart } };
        }

        case "uncomplete": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart." }], details: { error: true } };
          if (!params.goalId || !params.actionIndex) {
            return { content: [{ type: "text", text: "goalId and actionIndex required" }], details: { error: true } };
          }
          const goal = chart.supportingGoals.find(g => g.id === params.goalId);
          const action = goal?.actions[params.actionIndex - 1];
          if (!action) return { content: [{ type: "text", text: "Action not found" }], details: { error: true } };
          action.completed = false;
          action.completedAt = undefined;
          store.saveOW64(chart);
          return { content: [{ type: "text", text: `↩️ Uncompleted: ${action.id}` }], details: { action: "uncomplete", chart } };
        }

        case "promote_habit": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart." }], details: { error: true } };
          if (!params.goalId || !params.actionIndex) {
            return { content: [{ type: "text", text: "goalId and actionIndex required" }], details: { error: true } };
          }
          const goal = chart.supportingGoals.find(g => g.id === params.goalId);
          const action = goal?.actions[params.actionIndex - 1];
          if (!action || !action.text) return { content: [{ type: "text", text: "Action not found or empty" }], details: { error: true } };

          action.isHabit = true;
          store.saveOW64(chart);

          // Also create the habit
          const habits = store.getHabits();
          const existing = habits.find(h => h.actionId === action.id);
          if (!existing) {
            habits.push({
              id: `habit-${action.id}`,
              actionId: action.id,
              name: action.text,
              frequency: "daily",
              active: true,
              createdAt: new Date().toISOString(),
            });
            store.saveHabits(habits);
          }

          return { content: [{ type: "text", text: `🔄 Promoted to daily habit: ${action.text}` }], details: { action: "promote_habit", chart } };
        }

        case "export": {
          const chart = store.getOW64();
          if (!chart) return { content: [{ type: "text", text: "No chart to export." }], details: { error: true } };
          const lines = [`# Open Window 64`, "", `**⭐ ${chart.northStar}**`, ""];
          for (const g of chart.supportingGoals) {
            lines.push(`## Goal ${g.id}: ${g.title || "(untitled)"}`);
            for (const a of g.actions) {
              const mark = a.completed ? "[x]" : "[ ]";
              const habit = a.isHabit ? " 🔄" : "";
              lines.push(`- ${mark} ${a.id}: ${a.text || "(empty)"}${habit}`);
            }
            lines.push("");
          }
          return { content: [{ type: "text", text: lines.join("\n") }], details: { action: "export", chart } };
        }

        default:
          return { content: [{ type: "text", text: `Unknown action: ${params.action}` }], details: { error: true } };
      }
    },

    renderCall(args, theme) {
      let text = theme.fg("toolTitle", theme.bold("harada_ow64 ")) + theme.fg("muted", args.action);
      if (args.goalId) text += theme.fg("accent", ` G${args.goalId}`);
      if (args.actionIndex) text += theme.fg("dim", `-${args.actionIndex}`);
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
