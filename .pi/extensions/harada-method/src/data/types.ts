// ============================================================
// Harada Method — Core Data Types
// ============================================================

/** Long-term Goal Form (目標達成シート) */
export interface GoalForm {
  northStar: string;
  purpose: string;
  deadline: string; // ISO date
  currentState: string;
  gapAnalysis: string;
  obstacles: string[];
  supportNeeded: string[];
  affirmation: string;
  createdAt: string;
  updatedAt: string;
}

/** A single supporting goal in the OW64 chart */
export interface SupportingGoal {
  id: number; // 1-8
  title: string;
  actions: ActionItem[];
}

/** A single action item in the OW64 chart */
export interface ActionItem {
  id: string; // "1-1" through "8-8"
  goalId: number;
  text: string;
  completed: boolean;
  isHabit: boolean;
  completedAt?: string;
}

/** Open Window 64 Chart */
export interface OW64Chart {
  northStar: string;
  supportingGoals: SupportingGoal[];
}

/** A tracked daily habit */
export interface Habit {
  id: string;
  actionId?: string; // Links to OW64 action, if promoted
  name: string;
  frequency: "daily" | "weekday" | "weekly";
  active: boolean;
  createdAt: string;
}

/** Daily habit completion log: { "2026-02-12": { "habit-1": true, ... } } */
export interface HabitLog {
  [date: string]: {
    [habitId: string]: boolean;
  };
}

/** A single daily journal entry */
export interface JournalEntry {
  date: string; // "YYYY-MM-DD"
  wentWell: string[];
  didntGoWell: string[];
  learnings: string[];
  tomorrowFocus: string[];
  mood: 1 | 2 | 3 | 4 | 5;
  energy: 1 | 2 | 3 | 4 | 5;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

/** Computed analytics snapshot */
export interface ProgressSnapshot {
  ow64Completion: number;
  goalCompletion: { goalId: number; title: string; completed: number; total: number; pct: number }[];
  totalActionsCompleted: number;
  totalActions: number;
  habitStreak: number;
  longestStreak: number;
  habitCompletionRate30d: number;
  journalStreak: number;
  journalTotal: number;
  daysToDeadline: number;
  daysSinceStart: number;
  todayHabitsCompleted: number;
  todayHabitsTotal: number;
  avgMood30d: number | null;
  avgEnergy30d: number | null;
}

/** All Harada data in one bundle */
export interface HaradaData {
  goalForm: GoalForm | null;
  ow64: OW64Chart | null;
  habits: Habit[];
  habitLog: HabitLog;
  journals: { [date: string]: JournalEntry };
}
