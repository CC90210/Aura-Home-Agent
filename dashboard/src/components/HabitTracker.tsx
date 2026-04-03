"use client";

import {
  Flame,
  Check,
  Clock,
  Dumbbell,
  Salad,
  Monitor,
  Moon,
  Star,
  type LucideProps,
} from "lucide-react";
import type { HabitEntry } from "@/lib/types";

// Maps the string icon name stored on HabitEntry to a Lucide component.
const HABIT_ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  Dumbbell,
  Salad,
  Monitor,
  Moon,
  Star,
  Flame,
};

// ---------------------------------------------------------------------------
// HabitRow
// ---------------------------------------------------------------------------

interface HabitRowProps {
  habit: HabitEntry;
  onToggle: (habitId: string) => void;
}

function HabitRow({ habit, onToggle }: HabitRowProps) {
  const HabitIcon = HABIT_ICON_MAP[habit.icon] ?? Star;

  return (
    <button
      onClick={() => onToggle(habit.id)}
      role="checkbox"
      aria-checked={habit.completed}
      aria-label={`${habit.name} — ${habit.completed ? "completed" : "pending"}`}
      className={[
        "flex items-center gap-3 w-full rounded-xl px-3 py-2.5 text-left",
        "transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        "active:scale-[0.98]",
        habit.completed
          ? "border border-aura-green/22"
          : "border border-aura-border/40 hover:border-aura-border",
      ].join(" ")}
      style={
        habit.completed
          ? { background: "rgba(16,185,129,0.08)" }
          : { background: "rgba(26,26,62,0.40)" }
      }
    >
      {/* Checkbox circle */}
      <span
        className={[
          "shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all",
          habit.completed ? "border-aura-green" : "border-aura-border",
        ].join(" ")}
        style={
          habit.completed
            ? { background: "#10B981", boxShadow: "0 0 8px rgba(16,185,129,0.40)" }
            : undefined
        }
        aria-hidden="true"
      >
        {habit.completed && (
          <Check size={12} strokeWidth={3} className="text-white" />
        )}
      </span>

      {/* Icon */}
      <HabitIcon
        size={16}
        className={habit.completed ? "text-aura-green shrink-0" : "text-aura-text-muted shrink-0"}
        aria-hidden="true"
      />

      {/* Name + time */}
      <div className="flex flex-col gap-0 min-w-0 flex-1">
        <span
          className={[
            "text-sm font-medium leading-tight",
            habit.completed ? "text-aura-text line-through opacity-60" : "text-aura-text",
          ].join(" ")}
        >
          {habit.name}
        </span>
        <div className="flex items-center gap-1 mt-0.5">
          <Clock size={10} className="text-aura-text-muted" aria-hidden="true" />
          <span className="text-xs text-aura-text-muted">{habit.target_time}</span>
        </div>
      </div>

      {/* Streak */}
      <div className="shrink-0 flex items-center gap-1">
        <Flame
          size={14}
          className={habit.streak > 0 ? "text-aura-amber" : "text-aura-border"}
          aria-hidden="true"
        />
        <span
          className={[
            "text-xs font-bold tabular-nums",
            habit.streak > 0 ? "text-aura-amber" : "text-aura-border",
          ].join(" ")}
        >
          {habit.streak}
        </span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// HabitTracker
// ---------------------------------------------------------------------------

interface HabitTrackerProps {
  habits: HabitEntry[];
  onToggle: (habitId: string) => void;
}

export function HabitTracker({ habits, onToggle }: HabitTrackerProps) {
  const completedCount  = habits.filter((h) => h.completed).length;
  const totalCount      = habits.length;
  const allDone         = completedCount === totalCount && totalCount > 0;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div
      className="glass-card rounded-2xl p-4 flex flex-col gap-4"
      style={{ animation: "slide-up 0.4s ease-out both" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Flame size={15} className="text-aura-amber" aria-hidden="true" />
          <h2 className="text-xs font-semibold text-aura-text-muted uppercase tracking-wider">
            Today
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {allDone && (
            <span
              className="text-xs font-semibold text-aura-green"
              style={{ animation: "fade-in 0.3s ease-out" }}
            >
              All done
            </span>
          )}
          <span className="text-xs font-bold text-aura-text tabular-nums">
            {completedCount}/{totalCount}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div
        className="h-1.5 rounded-full overflow-hidden"
        style={{ background: "rgba(30,30,64,1)" }}
        role="progressbar"
        aria-valuenow={completedCount}
        aria-valuemin={0}
        aria-valuemax={totalCount}
        aria-label="Habit completion progress"
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${progressPercent}%`,
            background: allDone
              ? "#10B981"
              : "linear-gradient(90deg, #7C3AED 0%, #3B82F6 100%)",
            boxShadow: allDone
              ? "0 0 8px rgba(16,185,129,0.50)"
              : "0 0 8px rgba(124,58,237,0.40)",
          }}
        />
      </div>

      {/* Habit list */}
      <div className="flex flex-col gap-2">
        {habits.length === 0 ? (
          <p className="text-xs text-aura-text-muted text-center py-2">
            No habits configured.
          </p>
        ) : (
          habits.map((habit) => (
            <HabitRow key={habit.id} habit={habit} onToggle={onToggle} />
          ))
        )}
      </div>
    </div>
  );
}
