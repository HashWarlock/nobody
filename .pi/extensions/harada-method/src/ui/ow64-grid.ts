/**
 * OW64 Mandala Grid Overlay
 *
 * Displays the Open Window 64 chart in a navigable grid.
 * Center shows the north star, surrounding cells show goals and actions.
 */

import type { ExtensionContext, Theme } from "@mariozechner/pi-coding-agent";
import { matchesKey, truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";
import type { HaradaData, SupportingGoal } from "../data/types.js";

class OW64GridComponent {
  private data: HaradaData;
  private theme: Theme;
  private done: (result: void) => void;
  private selectedGoal = 0; // 0 = center, 1-8 = goals
  private cachedWidth?: number;
  private cachedLines?: string[];

  constructor(data: HaradaData, theme: Theme, done: (result: void) => void) {
    this.data = data;
    this.theme = theme;
    this.done = done;
  }

  handleInput(data: string): void {
    if (matchesKey(data, "escape") || matchesKey(data, "q")) {
      this.done();
      return;
    }
    if (matchesKey(data, "right") || matchesKey(data, "tab")) {
      this.selectedGoal = (this.selectedGoal + 1) % 9;
      this.invalidate();
    }
    if (matchesKey(data, "left") || matchesKey(data, "shift+tab")) {
      this.selectedGoal = (this.selectedGoal - 1 + 9) % 9;
      this.invalidate();
    }
    if (matchesKey(data, "down")) {
      this.selectedGoal = Math.min(8, this.selectedGoal + 3);
      this.invalidate();
    }
    if (matchesKey(data, "up")) {
      this.selectedGoal = Math.max(0, this.selectedGoal - 3);
      this.invalidate();
    }
  }

  render(width: number): string[] {
    if (this.cachedLines && this.cachedWidth === width) {
      return this.cachedLines;
    }

    const th = this.theme;
    const chart = this.data.ow64;
    const innerW = Math.min(width - 2, 76);
    const lines: string[] = [];

    const pad = (content: string, w: number) => {
      const vis = visibleWidth(content);
      return content + " ".repeat(Math.max(0, w - vis));
    };
    const row = (content: string) =>
      th.fg("border", "│") + " " + pad(content, innerW - 2) + " " + th.fg("border", "│");

    lines.push(th.fg("border", `╭${"─".repeat(innerW)}╮`));
    lines.push(row(th.fg("accent", th.bold("📊 OPEN WINDOW 64"))));
    lines.push(row(""));

    if (!chart) {
      lines.push(row(th.fg("dim", "No OW64 chart set up.")));
      lines.push(th.fg("border", `╰${"─".repeat(innerW)}╯`));
      this.cachedWidth = width;
      this.cachedLines = lines;
      return lines;
    }

    // Grid overview — show 3x3 grid of goal summaries
    const goals = chart.supportingGoals;
    // Layout: [G1 G2 G3] [G4 ⭐ G5] [G6 G7 G8]
    const gridOrder = [
      [goals[0], goals[1], goals[2]],
      [goals[3], null, goals[4]],   // null = center (north star)
      [goals[5], goals[6], goals[7]],
    ];
    const cellW = Math.floor((innerW - 8) / 3);

    for (const gridRow of gridOrder) {
      // Goal title row
      let titleLine = "  ";
      for (const cell of gridRow) {
        if (cell === null || cell === undefined) {
          const ns = truncateToWidth("⭐ " + (chart.northStar || ""), cellW - 2);
          const isSelected = this.selectedGoal === 0;
          titleLine += isSelected ? th.fg("accent", th.bold(`[${ns}]`)) : th.fg("warning", `[${ns}]`);
          titleLine += " ".repeat(Math.max(0, cellW - visibleWidth(ns) - 2));
        } else {
          const done = cell.actions.filter(a => a.completed).length;
          const pct = cell.actions.length > 0 ? Math.round((done / cell.actions.length) * 100) : 0;
          const label = truncateToWidth(`G${cell.id}: ${cell.title || "—"}`, cellW - 8);
          const isSelected = this.selectedGoal === cell.id;
          const pctStr = `${pct}%`;
          if (isSelected) {
            titleLine += th.fg("accent", th.bold(label)) + " " + th.fg("success", pctStr);
          } else {
            titleLine += th.fg("text", label) + " " + th.fg("dim", pctStr);
          }
          titleLine += " ".repeat(Math.max(0, cellW - visibleWidth(label) - visibleWidth(pctStr) - 1));
        }
        titleLine += "  ";
      }
      lines.push(row(truncateToWidth(titleLine, innerW - 4)));

      // Progress bar row
      let barLine = "  ";
      for (const cell of gridRow) {
        if (cell === null || cell === undefined) {
          barLine += " ".repeat(cellW) + "  ";
        } else {
          const done = cell.actions.filter(a => a.completed).length;
          const pct = cell.actions.length > 0 ? Math.round((done / cell.actions.length) * 100) : 0;
          const barW = cellW - 2;
          const filled = Math.round((pct / 100) * barW);
          barLine += th.fg("success", "█".repeat(filled)) + th.fg("dim", "░".repeat(barW - filled));
          barLine += "    ";
        }
      }
      lines.push(row(truncateToWidth(barLine, innerW - 4)));
      lines.push(row(""));
    }

    // Detail view for selected goal
    lines.push(row(th.fg("border", "─".repeat(innerW - 4))));

    if (this.selectedGoal === 0) {
      lines.push(row(th.fg("accent", th.bold("⭐ NORTH STAR"))));
      lines.push(row(th.fg("text", truncateToWidth(chart.northStar, innerW - 4))));
      if (this.data.goalForm) {
        lines.push(row(th.fg("dim", `Purpose: ${truncateToWidth(this.data.goalForm.purpose, innerW - 14)}`))); 
        lines.push(row(th.fg("dim", `Affirmation: ${truncateToWidth(this.data.goalForm.affirmation, innerW - 17)}`))); 
      }
    } else {
      const goal = goals[this.selectedGoal - 1];
      if (goal) {
        const done = goal.actions.filter(a => a.completed).length;
        lines.push(row(th.fg("accent", th.bold(`Goal ${goal.id}: ${goal.title || "(untitled)"}  [${done}/${goal.actions.length}]`))));
        lines.push(row(""));
        for (const action of goal.actions) {
          if (!action.text) continue;
          const mark = action.completed ? th.fg("success", "✅") : th.fg("dim", "☐ ");
          const habit = action.isHabit ? th.fg("warning", " 🔄") : "";
          lines.push(row(`  ${mark} ${th.fg("dim", action.id)} ${th.fg("text", truncateToWidth(action.text, innerW - 14))}${habit}`));
        }
      }
    }

    lines.push(row(""));

    // Legend
    lines.push(row(th.fg("success", "🟢") + th.fg("dim", " done  ") + th.fg("dim", "☐  todo  ") + th.fg("warning", "🔄") + th.fg("dim", " habit")));
    lines.push(row(th.fg("dim", "  ←→ select goal • ↑↓ navigate • q/Esc close")));
    lines.push(th.fg("border", `╰${"─".repeat(innerW)}╯`));

    this.cachedWidth = width;
    this.cachedLines = lines;
    return lines;
  }

  invalidate(): void {
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }
}

export async function showOW64Grid(ctx: ExtensionContext, data: HaradaData): Promise<void> {
  await ctx.ui.custom<void>(
    (_tui, theme, _kb, done) => new OW64GridComponent(data, theme, done),
    {
      overlay: true,
      overlayOptions: {
        anchor: "center",
        width: 80,
        maxHeight: "90%",
      },
    },
  );
}
