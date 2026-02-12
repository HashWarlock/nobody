// ============================================================
// Harada Method — Data Persistence Layer
// ============================================================

import * as fs from "node:fs";
import * as path from "node:path";
import type { GoalForm, Habit, HabitLog, HaradaData, JournalEntry, OW64Chart } from "./types.js";

export class HaradaStore {
  private dataDir: string;

  constructor(cwd: string) {
    this.dataDir = path.join(cwd, ".pi", "harada");
    this.ensureDir(this.dataDir);
    this.ensureDir(path.join(this.dataDir, "journal"));
  }

  // ── Goal Form ──────────────────────────────────────────

  getGoalForm(): GoalForm | null {
    return this.readJson<GoalForm>("goal-form.json");
  }

  saveGoalForm(form: GoalForm): void {
    form.updatedAt = new Date().toISOString();
    this.writeJson("goal-form.json", form);
  }

  // ── OW64 Chart ─────────────────────────────────────────

  getOW64(): OW64Chart | null {
    return this.readJson<OW64Chart>("ow64.json");
  }

  saveOW64(chart: OW64Chart): void {
    this.writeJson("ow64.json", chart);
  }

  // ── Habits ─────────────────────────────────────────────

  getHabits(): Habit[] {
    return this.readJson<Habit[]>("habits.json") ?? [];
  }

  saveHabits(habits: Habit[]): void {
    this.writeJson("habits.json", habits);
  }

  getHabitLog(): HabitLog {
    return this.readJson<HabitLog>("habit-log.json") ?? {};
  }

  saveHabitLog(log: HabitLog): void {
    this.writeJson("habit-log.json", log);
  }

  // ── Journal ────────────────────────────────────────────

  getJournalEntry(date: string): JournalEntry | null {
    return this.readJson<JournalEntry>(path.join("journal", `${date}.json`));
  }

  saveJournalEntry(entry: JournalEntry): void {
    entry.updatedAt = new Date().toISOString();
    this.writeJson(path.join("journal", `${entry.date}.json`), entry);
  }

  listJournalDates(): string[] {
    const journalDir = path.join(this.dataDir, "journal");
    if (!fs.existsSync(journalDir)) return [];
    return fs.readdirSync(journalDir)
      .filter(f => f.endsWith(".json"))
      .map(f => f.replace(".json", ""))
      .sort()
      .reverse();
  }

  // ── All Data ───────────────────────────────────────────

  getAllData(): HaradaData {
    const journals: { [date: string]: JournalEntry } = {};
    for (const date of this.listJournalDates()) {
      const entry = this.getJournalEntry(date);
      if (entry) journals[date] = entry;
    }
    return {
      goalForm: this.getGoalForm(),
      ow64: this.getOW64(),
      habits: this.getHabits(),
      habitLog: this.getHabitLog(),
      journals,
    };
  }

  // ── Helpers ────────────────────────────────────────────

  private readJson<T>(filename: string): T | null {
    const filepath = path.join(this.dataDir, filename);
    if (!fs.existsSync(filepath)) return null;
    try {
      const raw = fs.readFileSync(filepath, "utf-8");
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  private writeJson(filename: string, data: unknown): void {
    const filepath = path.join(this.dataDir, filename);
    const dir = path.dirname(filepath);
    this.ensureDir(dir);
    const tmp = filepath + ".tmp";
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), "utf-8");
    fs.renameSync(tmp, filepath);
  }

  private ensureDir(dir: string): void {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }
}
