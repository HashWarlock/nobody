/**
 * Harada Dashboard Overlay
 *
 * A centered overlay showing:
 * - North star goal and timeline
 * - OW64 progress bars per supporting goal
 * - Today's habit checklist
 * - Streaks, rates, mood/energy averages
 */

import type { ExtensionContext, Theme } from "@mariozechner/pi-coding-agent";
import { matchesKey, truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";
import { calcProgressSnapshot, calcTodayHabits, today } from "../data/analytics.js";
import type { HaradaData, ProgressSnapshot } from "../data/types.js";

type Section = "ow64" | "habits" | "stats";

class DashboardComponent {
  private data: HaradaData;
  private snapshot: ProgressSnapshot;
  private theme: Theme;
  private done: (result: void) => void;
  private section: Section = "ow64";
  private cachedWidth?: number;
  private cachedLines?: string[];

  constructor(data: HaradaData, theme: Theme, done: (result: void) => void) {
    this.data = data;
    this.snapshot = calcProgressSnapshot(data);
    this.theme = theme;
    this.done = done;
  }

  handleInput(data: string): void {
    if (matchesKey(data, "escape") || matchesKey(data, "q")) {
      this.done();
      return;
    }
    if (matchesKey(data, "tab") || matchesKey(data, "down")) {
      const sections: Section[] = ["ow64", "habits", "stats"];
      const idx = sections.indexOf(this.section);
      this.section = sections[(idx + 1) % sections.length]!;
      this.invalidate();
    }
    if (matchesKey(data, "shift+tab") || matchesKey(data, "up")) {
      const sections: Section[] = ["ow64", "habits", "stats"];
      const idx = sections.indexOf(this.section);
      this.section = sections[(idx - 1 + sections.length) % sections.length]!;
      this.invalidate();
    }
    if (matchesKey(data, "r")) {
      this.snapshot = calcProgressSnapshot(this.data);
      this.invalidate();
    }
  }

  render(width: number): string[] {
    if (this.cachedLines && this.cachedWidth === width) {
      return this.cachedLines;
    }

    const th = this.theme;
    const s = this.snapshot;
    const innerW = Math.min(width - 2, 72);
    const lines: string[] = [];

    const pad = (content: string, w: number) => {
      const vis = visibleWidth(content);
      return content + " ".repeat(Math.max(0, w - vis));
    };
    const row = (content: string) =>
      th.fg("border", "│") + " " + pad(content, innerW - 2) + " " + th.fg("border", "│");
    const hr = (char = "─") => th.fg("border", `├${char.repeat(innerW)}┤`);

    // Top border
    lines.push(th.fg("border", `╭${"─".repeat(innerW)}╮`));

    // Title
    lines.push(row(th.fg("accent", th.bold("🎯 HARADA DASHBOARD"))));
    lines.push(row(""));

    // North Star
    const ns = this.data.goalForm?.northStar ?? "No goal set";
    lines.push(row(th.fg("accent", "⭐ ") + th.fg("text", truncateToWidth(ns, innerW - 6))));

    // Timeline
    const timeline = s.daysToDeadline > 0
      ? `📅 Day ${s.daysSinceStart} │ ${s.daysToDeadline} days remaining`
      : `📅 Day ${s.daysSinceStart}`;
    const streak = s.habitStreak > 0 ? `  🔥 ${s.habitStreak}-day streak` : "";
    lines.push(row(th.fg("muted", timeline + streak)));

    lines.push(hr());

    // OW64 Section
    const ow64Active = this.section === "ow64";
    const ow64Label = ow64Active ? th.fg("accent", th.bold("📊 OW64 Progress")) : th.fg("muted", "📊 OW64 Progress");
    lines.push(row(ow64Label));

    for (const g of s.goalCompletion) {
      if (!g.title) continue;
      const barWidth = 12;
      const filled = Math.round((g.pct / 100) * barWidth);
      const bar = th.fg("success", "█".repeat(filled)) + th.fg("dim", "░".repeat(barWidth - filled));
      const label = truncateToWidth(`${g.goalId}. ${g.title}`, 25).padEnd(25);
      lines.push(row(`  ${th.fg("text", label)} ${bar} ${th.fg("muted", `${g.pct}%`.padStart(4))} ${th.fg("dim", `[${g.completed}/${g.total}]`)}`));
    }

    // Overall bar
    const overallFilled = Math.round((s.ow64Completion / 100) * 30);
    const overallBar = th.fg("accent", "█".repeat(overallFilled)) + th.fg("dim", "░".repeat(30 - overallFilled));
    lines.push(row(th.fg("text", `  Overall: ${overallBar} ${s.ow64Completion}%  [${s.totalActionsCompleted}/${s.totalActions}]`)));

    lines.push(hr());

    // Habits Section
    const habitsActive = this.section === "habits";
    const habitsLabel = habitsActive ? th.fg("accent", th.bold("✅ Today's Habits")) : th.fg("muted", "✅ Today's Habits");
    lines.push(row(habitsLabel));

    const activeHabits = this.data.habits.filter(h => h.active);
    const todayStr = today();
    const dayLog = this.data.habitLog[todayStr] ?? {};

    if (activeHabits.length === 0) {
      lines.push(row(th.fg("dim", "  No habits set up yet")));
    } else {
      for (const h of activeHabits) {
        const done = dayLog[h.id] === true;
        const mark = done ? th.fg("success", "✅") : th.fg("dim", "☐ ");
        const name = done ? th.fg("muted", h.name) : th.fg("text", h.name);
        lines.push(row(`  ${mark} ${truncateToWidth(name, innerW - 8)}`));
      }
      const todayH = calcTodayHabits(activeHabits, this.data.habitLog);
      const pct = todayH.total > 0 ? Math.round((todayH.completed / todayH.total) * 100) : 0;
      lines.push(row(th.fg("muted", `  ${todayH.completed}/${todayH.total} done (${pct}%)`.padStart(innerW - 4))));
    }

    lines.push(hr());

    // Stats Section
    const statsActive = this.section === "stats";
    const statsLabel = statsActive ? th.fg("accent", th.bold("📊 Stats")) : th.fg("muted", "📊 Stats");
    lines.push(row(statsLabel));
    lines.push(row(
      th.fg("muted", `  30-Day Habit Rate: ${th.fg("text", `${s.habitCompletionRate30d}%`)}`)
      + th.fg("muted", `  │  📓 Journal: ${th.fg("text", `${s.journalStreak}d streak`)} (${s.journalTotal} total)`)
    ));
    const moodStr = s.avgMood30d !== null ? `${s.avgMood30d}/5` : "—";
    const energyStr = s.avgEnergy30d !== null ? `${s.avgEnergy30d}/5` : "—";
    lines.push(row(
      th.fg("muted", `  😊 Avg Mood: ${th.fg("text", moodStr)}`)
      + th.fg("muted", `  │  ⚡ Avg Energy: ${th.fg("text", energyStr)}`)
    ));

    lines.push(row(""));

    // Help
    lines.push(row(th.fg("dim", "  ↑↓/Tab navigate sections • r refresh • q/Esc close")));

    // Bottom border
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

export async function showDashboard(ctx: ExtensionContext, data: HaradaData): Promise<void> {
  await ctx.ui.custom<void>(
    (_tui, theme, _kb, done) => new DashboardComponent(data, theme, done),
    {
      overlay: true,
      overlayOptions: {
        anchor: "center",
        width: 76,
        maxHeight: "90%",
      },
    },
  );
}
