import { StringEnum } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import type { HaradaStore } from "../data/store.js";
import type { GoalForm } from "../data/types.js";

const GoalFormParams = Type.Object({
  action: StringEnum(["setup", "view", "update", "export"] as const),
  northStar: Type.Optional(Type.String({ description: "The ultimate north star goal" })),
  purpose: Type.Optional(Type.String({ description: "Why this goal matters (deep motivation)" })),
  deadline: Type.Optional(Type.String({ description: "Target date (YYYY-MM-DD)" })),
  currentState: Type.Optional(Type.String({ description: "Honest assessment of current state" })),
  gapAnalysis: Type.Optional(Type.String({ description: "Gap between current state and goal" })),
  obstacles: Type.Optional(Type.Array(Type.String(), { description: "Expected challenges" })),
  supportNeeded: Type.Optional(Type.Array(Type.String(), { description: "Resources/people needed" })),
  affirmation: Type.Optional(Type.String({ description: "Daily affirmation statement" })),
});

export function registerGoalFormTool(pi: ExtensionAPI, getStore: () => HaradaStore): void {
  pi.registerTool({
    name: "harada_goal_form",
    label: "Harada Goal Form",
    description:
      "Manage the Harada Method long-term goal form. Actions: setup (create new), view (display current), update (modify fields), export (as markdown). The goal form captures: northStar, purpose, deadline, currentState, gapAnalysis, obstacles[], supportNeeded[], affirmation.",
    parameters: GoalFormParams,

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const store = getStore();

      switch (params.action) {
        case "setup": {
          if (!params.northStar) {
            return { content: [{ type: "text", text: "Error: northStar is required for setup" }], details: { error: true } };
          }
          const now = new Date().toISOString();
          const form: GoalForm = {
            northStar: params.northStar,
            purpose: params.purpose ?? "",
            deadline: params.deadline ?? "",
            currentState: params.currentState ?? "",
            gapAnalysis: params.gapAnalysis ?? "",
            obstacles: params.obstacles ?? [],
            supportNeeded: params.supportNeeded ?? [],
            affirmation: params.affirmation ?? "",
            createdAt: now,
            updatedAt: now,
          };
          store.saveGoalForm(form);
          return {
            content: [{ type: "text", text: `✅ Goal form created!\n\n⭐ North Star: ${form.northStar}\n💫 Affirmation: ${form.affirmation || "(not set)"}\n📅 Deadline: ${form.deadline || "(not set)"}` }],
            details: { action: "setup", form },
          };
        }

        case "view": {
          const form = store.getGoalForm();
          if (!form) {
            return { content: [{ type: "text", text: "No goal form set up yet. Use action 'setup' to create one." }], details: { action: "view", form: null } };
          }
          const lines = [
            `⭐ North Star: ${form.northStar}`,
            `💡 Purpose: ${form.purpose || "(not set)"}`,
            `📅 Deadline: ${form.deadline || "(not set)"}`,
            `📍 Current State: ${form.currentState || "(not set)"}`,
            `📊 Gap Analysis: ${form.gapAnalysis || "(not set)"}`,
            `🚧 Obstacles: ${form.obstacles.length > 0 ? form.obstacles.join(", ") : "(none)"}`,
            `🤝 Support Needed: ${form.supportNeeded.length > 0 ? form.supportNeeded.join(", ") : "(none)"}`,
            `💫 Affirmation: ${form.affirmation || "(not set)"}`,
          ];
          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "view", form },
          };
        }

        case "update": {
          const form = store.getGoalForm();
          if (!form) {
            return { content: [{ type: "text", text: "No goal form exists. Use 'setup' first." }], details: { error: true } };
          }
          const updated: string[] = [];
          if (params.northStar !== undefined) { form.northStar = params.northStar; updated.push("northStar"); }
          if (params.purpose !== undefined) { form.purpose = params.purpose; updated.push("purpose"); }
          if (params.deadline !== undefined) { form.deadline = params.deadline; updated.push("deadline"); }
          if (params.currentState !== undefined) { form.currentState = params.currentState; updated.push("currentState"); }
          if (params.gapAnalysis !== undefined) { form.gapAnalysis = params.gapAnalysis; updated.push("gapAnalysis"); }
          if (params.obstacles !== undefined) { form.obstacles = params.obstacles; updated.push("obstacles"); }
          if (params.supportNeeded !== undefined) { form.supportNeeded = params.supportNeeded; updated.push("supportNeeded"); }
          if (params.affirmation !== undefined) { form.affirmation = params.affirmation; updated.push("affirmation"); }
          store.saveGoalForm(form);
          return {
            content: [{ type: "text", text: `✅ Updated: ${updated.join(", ")}` }],
            details: { action: "update", form, updated },
          };
        }

        case "export": {
          const form = store.getGoalForm();
          if (!form) {
            return { content: [{ type: "text", text: "No goal form to export." }], details: { error: true } };
          }
          const md = [
            "# Harada Method — Long-term Goal Form",
            "",
            `## ⭐ North Star Goal`,
            form.northStar,
            "",
            `## 💡 Purpose`,
            form.purpose || "_Not defined_",
            "",
            `## 📅 Deadline`,
            form.deadline || "_Not set_",
            "",
            `## 📍 Current State`,
            form.currentState || "_Not assessed_",
            "",
            `## 📊 Gap Analysis`,
            form.gapAnalysis || "_Not analyzed_",
            "",
            `## 🚧 Expected Obstacles`,
            ...form.obstacles.map(o => `- ${o}`),
            "",
            `## 🤝 Support Needed`,
            ...form.supportNeeded.map(s => `- ${s}`),
            "",
            `## 💫 Daily Affirmation`,
            `> ${form.affirmation || "_Not set_"}`,
          ].join("\n");
          return {
            content: [{ type: "text", text: md }],
            details: { action: "export", form },
          };
        }

        default:
          return { content: [{ type: "text", text: `Unknown action: ${params.action}` }], details: { error: true } };
      }
    },

    renderCall(args, theme) {
      const text = theme.fg("toolTitle", theme.bold("harada_goal_form "))
        + theme.fg("muted", args.action);
      return new Text(text, 0, 0);
    },

    renderResult(result, _options, theme) {
      const text = result.content[0];
      const content = text?.type === "text" ? text.text : "";
      if (result.details?.error) {
        return new Text(theme.fg("error", content), 0, 0);
      }
      return new Text(theme.fg("success", "✓ ") + theme.fg("muted", content.split("\n")[0] ?? ""), 0, 0);
    },
  });
}
