// ============================================================
// Harada Method — Progress Analytics Engine
// ============================================================

import type { Habit, HabitLog, HaradaData, JournalEntry, OW64Chart, ProgressSnapshot } from "./types.js";

/** Get today's date as "YYYY-MM-DD" */
export function today(): string {
  return new Date().toISOString().split("T")[0]!;
}

/** Get a date N days ago as "YYYY-MM-DD" */
export function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split("T")[0]!;
}

/** Get all dates in a range (inclusive) */
export function dateRange(startDate: string, endDate: string): string[] {
  const dates: string[] = [];
  const current = new Date(startDate);
  const end = new Date(endDate);
  while (current <= end) {
    dates.push(current.toISOString().split("T")[0]!);
    current.setDate(current.getDate() + 1);
  }
  return dates;
}

/** Calculate OW64 completion stats */
export function calcOW64Completion(ow64: OW64Chart | null) {
  if (!ow64 || !ow64.supportingGoals.length) {
    return { total: 0, completed: 0, pct: 0, goals: [] };
  }
  const goals = ow64.supportingGoals.map(g => {
    const completed = g.actions.filter(a => a.completed).length;
    return {
      goalId: g.id,
      title: g.title,
      completed,
      total: g.actions.length,
      pct: g.actions.length > 0 ? Math.round((completed / g.actions.length) * 100) : 0,
    };
  });
  const total = goals.reduce((s, g) => s + g.total, 0);
  const completed = goals.reduce((s, g) => s + g.completed, 0);
  return {
    total,
    completed,
    pct: total > 0 ? Math.round((completed / total) * 100) : 0,
    goals,
  };
}

/** Calculate current habit streak (consecutive days with all active habits done) */
export function calcHabitStreak(habits: Habit[], log: HabitLog): { current: number; longest: number } {
  const activeHabits = habits.filter(h => h.active);
  if (activeHabits.length === 0) return { current: 0, longest: 0 };

  let current = 0;
  let longest = 0;
  let streak = 0;
  const d = new Date();

  // Walk backwards from today
  for (let i = 0; i < 365; i++) {
    const dateStr = d.toISOString().split("T")[0]!;
    const dayLog = log[dateStr];
    const allDone = dayLog && activeHabits.every(h => dayLog[h.id] === true);

    if (allDone) {
      streak++;
      if (i === current) current = streak; // only count from today backwards
    } else {
      if (i === 0) current = 0; // today not done yet, streak from yesterday
      longest = Math.max(longest, streak);
      streak = 0;
    }
    d.setDate(d.getDate() - 1);
  }
  longest = Math.max(longest, streak);
  return { current, longest };
}

/** 30-day habit completion rate */
export function calcHabitRate30d(habits: Habit[], log: HabitLog): number {
  const activeHabits = habits.filter(h => h.active);
  if (activeHabits.length === 0) return 0;

  let totalChecks = 0;
  let completedChecks = 0;
  const dates = dateRange(daysAgo(29), today());

  for (const date of dates) {
    const dayLog = log[date];
    for (const habit of activeHabits) {
      // Only count days relevant to frequency
      if (habit.frequency === "weekday") {
        const dow = new Date(date).getDay();
        if (dow === 0 || dow === 6) continue;
      }
      totalChecks++;
      if (dayLog && dayLog[habit.id] === true) completedChecks++;
    }
  }

  return totalChecks > 0 ? Math.round((completedChecks / totalChecks) * 100) : 0;
}

/** Calculate journal streak */
export function calcJournalStreak(journals: { [date: string]: JournalEntry }): number {
  let streak = 0;
  const d = new Date();
  for (let i = 0; i < 365; i++) {
    const dateStr = d.toISOString().split("T")[0]!;
    if (journals[dateStr]) {
      streak++;
    } else {
      break;
    }
    d.setDate(d.getDate() - 1);
  }
  return streak;
}

/** Average mood/energy over last 30 days */
export function calcAvg30d(journals: { [date: string]: JournalEntry }, field: "mood" | "energy"): number | null {
  const dates = dateRange(daysAgo(29), today());
  const values = dates
    .map(d => journals[d]?.[field])
    .filter((v): v is number => v !== undefined);
  if (values.length === 0) return null;
  return Math.round((values.reduce((s, v) => s + v, 0) / values.length) * 10) / 10;
}

/** Today's habit completion */
export function calcTodayHabits(habits: Habit[], log: HabitLog): { completed: number; total: number } {
  const activeHabits = habits.filter(h => h.active);
  const todayStr = today();
  const dayLog = log[todayStr] ?? {};
  const completed = activeHabits.filter(h => dayLog[h.id] === true).length;
  return { completed, total: activeHabits.length };
}

/** Full progress snapshot */
export function calcProgressSnapshot(data: HaradaData): ProgressSnapshot {
  const ow64 = calcOW64Completion(data.ow64);
  const streaks = calcHabitStreak(data.habits, data.habitLog);
  const todayH = calcTodayHabits(data.habits, data.habitLog);

  const deadline = data.goalForm?.deadline;
  const createdAt = data.goalForm?.createdAt;
  const now = new Date();

  return {
    ow64Completion: ow64.pct,
    goalCompletion: ow64.goals,
    totalActionsCompleted: ow64.completed,
    totalActions: ow64.total,
    habitStreak: streaks.current,
    longestStreak: streaks.longest,
    habitCompletionRate30d: calcHabitRate30d(data.habits, data.habitLog),
    journalStreak: calcJournalStreak(data.journals),
    journalTotal: Object.keys(data.journals).length,
    daysToDeadline: deadline ? Math.ceil((new Date(deadline).getTime() - now.getTime()) / 86400000) : -1,
    daysSinceStart: createdAt ? Math.floor((now.getTime() - new Date(createdAt).getTime()) / 86400000) : 0,
    todayHabitsCompleted: todayH.completed,
    todayHabitsTotal: todayH.total,
    avgMood30d: calcAvg30d(data.journals, "mood"),
    avgEnergy30d: calcAvg30d(data.journals, "energy"),
  };
}
