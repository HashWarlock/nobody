import { StringEnum } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { calcJournalStreak, today } from "../data/analytics.js";
import type { HaradaStore } from "../data/store.js";
import type { JournalEntry } from "../data/types.js";

const JournalParams = Type.Object({
  action: StringEnum(["write", "read", "list", "streak"] as const),
  date: Type.Optional(Type.String({ description: "Date (YYYY-MM-DD), defaults to today" })),
  wentWell: Type.Optional(Type.Array(Type.String(), { description: "Things that went well" })),
  didntGoWell: Type.Optional(Type.Array(Type.String(), { description: "Things that didn't go well" })),
  learnings: Type.Optional(Type.Array(Type.String(), { description: "Key learnings" })),
  tomorrowFocus: Type.Optional(Type.Array(Type.String(), { description: "Tomorrow's focus areas" })),
  mood: Type.Optional(Type.Number({ description: "Mood rating 1-5" })),
  energy: Type.Optional(Type.Number({ description: "Energy rating 1-5" })),
  notes: Type.Optional(Type.String({ description: "Additional notes" })),
  limit: Type.Optional(Type.Number({ description: "Number of entries for list (default 7)" })),
});

const MOOD_EMOJI: Record<number, string> = { 1: "😞", 2: "😐", 3: "🙂", 4: "😊", 5: "🤩" };
const ENERGY_EMOJI: Record<number, string> = { 1: "🪫", 2: "🔋", 3: "⚡", 4: "💪", 5: "🚀" };

export function registerJournalTool(pi: ExtensionAPI, getStore: () => HaradaStore): void {
  pi.registerTool({
    name: "harada_journal",
    label: "Harada Journal",
    description:
      "Daily reflection journal. Actions: write (create/update entry), read (view a day's entry), list (recent entries), streak (journaling streak). Fields: wentWell[], didntGoWell[], learnings[], tomorrowFocus[], mood (1-5), energy (1-5), notes.",
    parameters: JournalParams,

    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const store = getStore();
      const dateStr = params.date ?? today();

      switch (params.action) {
        case "write": {
          const existing = store.getJournalEntry(dateStr);
          const now = new Date().toISOString();

          const entry: JournalEntry = {
            date: dateStr,
            wentWell: params.wentWell ?? existing?.wentWell ?? [],
            didntGoWell: params.didntGoWell ?? existing?.didntGoWell ?? [],
            learnings: params.learnings ?? existing?.learnings ?? [],
            tomorrowFocus: params.tomorrowFocus ?? existing?.tomorrowFocus ?? [],
            mood: (params.mood ?? existing?.mood ?? 3) as 1 | 2 | 3 | 4 | 5,
            energy: (params.energy ?? existing?.energy ?? 3) as 1 | 2 | 3 | 4 | 5,
            notes: params.notes ?? existing?.notes,
            createdAt: existing?.createdAt ?? now,
            updatedAt: now,
          };

          store.saveJournalEntry(entry);

          return {
            content: [{ type: "text", text: `📓 Journal saved for ${dateStr}\n${MOOD_EMOJI[entry.mood] ?? ""} Mood: ${entry.mood}/5 | ${ENERGY_EMOJI[entry.energy] ?? ""} Energy: ${entry.energy}/5` }],
            details: { action: "write", entry },
          };
        }

        case "read": {
          const entry = store.getJournalEntry(dateStr);
          if (!entry) {
            return { content: [{ type: "text", text: `No journal entry for ${dateStr}` }], details: { action: "read", entry: null } };
          }

          const lines = [
            `📓 Journal — ${entry.date}`,
            `${MOOD_EMOJI[entry.mood] ?? ""} Mood: ${entry.mood}/5 | ${ENERGY_EMOJI[entry.energy] ?? ""} Energy: ${entry.energy}/5`,
            "",
            "✨ What went well:",
            ...entry.wentWell.map(w => `  • ${w}`),
            "",
            "🔴 What didn't go well:",
            ...entry.didntGoWell.map(w => `  • ${w}`),
            "",
            "💡 Learnings:",
            ...entry.learnings.map(l => `  • ${l}`),
            "",
            "🎯 Tomorrow's focus:",
            ...entry.tomorrowFocus.map(f => `  • ${f}`),
          ];
          if (entry.notes) {
            lines.push("", `📝 Notes: ${entry.notes}`);
          }

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "read", entry },
          };
        }

        case "list": {
          const dates = store.listJournalDates().slice(0, params.limit ?? 7);
          if (dates.length === 0) {
            return { content: [{ type: "text", text: "No journal entries yet." }], details: { action: "list", entries: [] } };
          }

          const lines = ["📓 Recent Journal Entries", ""];
          for (const d of dates) {
            const entry = store.getJournalEntry(d);
            if (!entry) continue;
            const mood = MOOD_EMOJI[entry.mood] ?? "";
            const energy = ENERGY_EMOJI[entry.energy] ?? "";
            const wellCount = entry.wentWell.length;
            lines.push(`  ${d}  ${mood} ${energy}  (${wellCount} wins, ${entry.didntGoWell.length} challenges)`);
          }

          const journals: { [date: string]: JournalEntry } = {};
          for (const d of dates) {
            const entry = store.getJournalEntry(d);
            if (entry) journals[d] = entry;
          }
          const streak = calcJournalStreak(journals);
          lines.push("", `📝 Journal streak: ${streak} days`);

          return {
            content: [{ type: "text", text: lines.join("\n") }],
            details: { action: "list", dates },
          };
        }

        case "streak": {
          const allDates = store.listJournalDates();
          const journals: { [date: string]: JournalEntry } = {};
          for (const d of allDates) {
            const entry = store.getJournalEntry(d);
            if (entry) journals[d] = entry;
          }
          const streak = calcJournalStreak(journals);
          return {
            content: [{ type: "text", text: `📝 Journal streak: ${streak} days (${allDates.length} total entries)` }],
            details: { action: "streak", streak, totalEntries: allDates.length },
          };
        }

        default:
          return { content: [{ type: "text", text: `Unknown action: ${params.action}` }], details: { error: true } };
      }
    },

    renderCall(args, theme) {
      let text = theme.fg("toolTitle", theme.bold("harada_journal ")) + theme.fg("muted", args.action);
      if (args.date) text += " " + theme.fg("dim", args.date);
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
