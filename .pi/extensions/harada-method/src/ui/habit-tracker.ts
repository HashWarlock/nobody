/**
 * Habit Tracker Overlay
 *
 * Weekly calendar view of habit completion with interactive checking.
 * Shows streaks, completion rates, and allows marking today's habits done.
 */

import type { ExtensionContext, Theme } from "@mariozechner/pi-coding-agent";
import { matchesKey, truncateToWidth, visibleWidth } from "@mariozechner/pi-tui";
import { calcHabitStreak, calcHabitRate30d, dateRange, today } from "../data/analytics.js";
import type { HaradaStore } from "../data/store.js";
import type { Habit, HabitLog, HaradaData } from "../data/types.js";

const DAY_NAMES = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

class HabitTrackerComponent {
  private habits: Habit[];
  private habitLog: HabitLog;
  private store: HaradaStore;
  private theme: Theme;
  private done: (result: void) => void;
  private selectedHabit = 0;
  private weekOffset = 0; // 0 = current week, -1 = last week, etc.
  private cachedWidth?: number;
  private cachedLines?: string[];

  constructor(data: HaradaData, store: HaradaStore, theme: Theme, done: (result: void) => void) {
    this.habits = data.habits.filter(h => h.active);
    this.habitLog = { ...data.habitLog };
    this.store = store;
    this.theme = theme;
    this.done = done;
  }

  handleInput(data: string): void {
    if (matchesKey(data, "escape") || matchesKey(data, "q")) {
      this.done();
      return;
    }
    if (matchesKey(data, "up")) {
      this.selectedHabit = Math.max(0, this.selectedHabit - 1);
      this.invalidate();
    }
    if (matchesKey(data, "down")) {
      this.selectedHabit = Math.min(this.habits.length - 1, this.selectedHabit + 1);
      this.invalidate();
    }
    if (matchesKey(data, "left")) {
      this.weekOffset--;
      this.invalidate();
    }
    if (matchesKey(data, "right")) {
      if (this.weekOffset < 0) this.weekOffset++;
      this.invalidate();
    }
    // Toggle today's habit
    if (matchesKey(data, "return") || matchesKey(data, "h") || matchesKey(data, "space")) {
      const habit = this.habits[this.selectedHabit];
      if (habit) {
        const todayStr = today();
        if (!this.habitLog[todayStr]) this.habitLog[todayStr] = {};
        const current = this.habitLog[todayStr]![habit.id] === true;
        this.habitLog[todayStr]![habit.id] = !current;
        this.store.saveHabitLog(this.habitLog);
        this.invalidate();
      }
    }
  }

  render(width: number): string[] {
    if (this.cachedLines && this.cachedWidth === width) {
      return this.cachedLines;
    }

    const th = this.theme;
    const innerW = Math.min(width - 2, 62);
    const lines: string[] = [];

    const pad = (content: string, w: number) => {
      const vis = visibleWidth(content);
      return content + " ".repeat(Math.max(0, w - vis));
    };
    const row = (content: string) =>
      th.fg("border", "│") + " " + pad(content, innerW - 2) + " " + th.fg("border", "│");

    // Calculate week dates
    const todayDate = new Date();
    const dayOfWeek = todayDate.getDay(); // 0=Sun
    const weekStart = new Date(todayDate);
    weekStart.setDate(weekStart.getDate() - dayOfWeek + (this.weekOffset * 7));
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);

    const weekDates = dateRange(
      weekStart.toISOString().split("T")[0]!,
      weekEnd.toISOString().split("T")[0]!,
    );

    const todayStr = today();

    lines.push(th.fg("border", `╭${"─".repeat(innerW)}╮`));
    lines.push(row(th.fg("accent", th.bold("📋 HABIT TRACKER"))));
    lines.push(row(""));

    // Week header
    const weekLabel = `Week of ${weekDates[0]} → ${weekDates[6]}`;
    const navHint = this.weekOffset < 0 ? " →" : "";
    lines.push(row(th.fg("muted", weekLabel + navHint)));
    lines.push(row(""));

    // Day headers
    const nameW = Math.min(20, innerW - 30);
    let headerLine = " ".repeat(nameW);
    for (let i = 0; i < 7; i++) {
      const isToday = weekDates[i] === todayStr;
      const dayLabel = DAY_NAMES[i]!;
      headerLine += isToday ? th.fg("accent", th.bold(dayLabel.padStart(4))) : th.fg("dim", dayLabel.padStart(4));
    }
    lines.push(row(headerLine));
    lines.push(row(th.fg("border", "─".repeat(innerW - 4))));

    // Habit rows
    for (let hi = 0; hi < this.habits.length; hi++) {
      const habit = this.habits[hi]!;
      const isSelected = hi === this.selectedHabit;
      const prefix = isSelected ? th.fg("accent", "▶ ") : "  ";
      const name = truncateToWidth(habit.name, nameW - 3);
      const styledName = isSelected ? th.fg("accent", name) : th.fg("text", name);

      let habitRow = prefix + styledName + " ".repeat(Math.max(0, nameW - visibleWidth(name) - 2));

      for (let di = 0; di < 7; di++) {
        const date = weekDates[di]!;
        const isFuture = date > todayStr;
        const done = this.habitLog[date]?.[habit.id] === true;

        if (isFuture) {
          habitRow += th.fg("dim", " — ");
        } else if (done) {
          habitRow += th.fg("success", " ✅ ");
        } else {
          habitRow += th.fg("dim", " ☐  ");
        }
      }
      lines.push(row(truncateToWidth(habitRow, innerW - 4)));
    }

    // Daily completion rates
    lines.push(row(th.fg("border", "─".repeat(innerW - 4))));
    let rateLine = "Rate".padEnd(nameW);
    for (let di = 0; di < 7; di++) {
      const date = weekDates[di]!;
      if (date > todayStr) {
        rateLine += "    ";
        continue;
      }
      const dayLog = this.habitLog[date] ?? {};
      const done = this.habits.filter(h => dayLog[h.id] === true).length;
      const rate = this.habits.length > 0 ? Math.round((done / this.habits.length) * 100) : 0;
      rateLine += th.fg(rate >= 80 ? "success" : rate >= 50 ? "warning" : "error", `${rate}%`.padStart(4));
    }
    lines.push(row(th.fg("muted", rateLine)));

    lines.push(row(""));

    // Stats
    const streaks = calcHabitStreak(this.habits, this.habitLog);
    const rate30d = calcHabitRate30d(this.habits, this.habitLog);

    lines.push(row(
      th.fg("muted", `🔥 Streak: ${th.fg("text", `${streaks.current} days`)}`)
      + th.fg("muted", `  │  🏆 Best: ${th.fg("text", `${streaks.longest} days`)}`)
      + th.fg("muted", `  │  📊 30d: ${th.fg("text", `${rate30d}%`)}`)
    ));

    lines.push(row(""));
    lines.push(row(th.fg("dim", "  ↑↓ select • Enter/Space check today • ←→ week • q close")));
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

export async function showHabitTracker(ctx: ExtensionContext, data: HaradaData, store: HaradaStore): Promise<void> {
  await ctx.ui.custom<void>(
    (_tui, theme, _kb, done) => new HabitTrackerComponent(data, store, theme, done),
    {
      overlay: true,
      overlayOptions: {
        anchor: "center",
        width: 66,
        maxHeight: "85%",
      },
    },
  );
}
