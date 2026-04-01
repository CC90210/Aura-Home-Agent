"use client";

import { Flame, Check, Clock } from "lucide-react";
import type { HabitEntry } from "@/lib/types";

interface HabitRowProps {
  habit: HabitEntry;
  onToggle: (habitId: string) => void;
}

function HabitRow({ habit, onToggle }: HabitRowProps) {
  return (
    <button
      onClick={() => onToggle(habit.id)}
      role="checkbox"
      aria-checked={habit.completed}
      aria-label={`${habit.name} — ${habit.completed ? "completed" : "pending"}`}
      className={[
        "flex items-center gap-3 w-full rounded-xl px-3 py-2.5",
        "transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        "text-left",
        habit.completed
          ? "bg-aura-green/10 border border-aura-green/25"
          : "bg-aura-card-hover/40 border border-aura-border/40 hover:border-aura-border",
      ].join(" ")}
    >
      {/* Checkbox circle */}
      <span
        className={[
          "shrink-0 w-6 h-6 rounded-full border-2 flex items-center justify-center transition-all",
          habit.completed
            ? "bg-aura-green border-aura-green shadow-aura-green"
            : "border-aura-border",
        ].join(" ")}
        aria-hidden="true"
      >
        {habit.completed && (
          <Check size={12} strokeWidth={3} className="text-white" />
        )}
      </span>

      {/* Icon + name */}
      <span className="text-lg leading-none" aria-hidden="true">
        {habit.icon}
      </span>
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

interface HabitTrackerProps {
  habits: HabitEntry[];
  onToggle: (habitId: string) => void;
}

export function HabitTracker({ habits, onToggle }: HabitTrackerProps) {
  const completedCount = habits.filter((h) => h.completed).length;
  const totalCount = habits.length;
  const allDone = completedCount === totalCount && totalCount > 0;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col gap-4 animate-[slide-up_0.4s_ease-out]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Flame size={16} className="text-aura-amber" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-aura-text-muted uppercase tracking-wider">
            Today
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {allDone && (
            <span className="text-xs font-semibold text-aura-green animate-[fade-in_0.3s_ease-out]">
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
        className="h-1.5 rounded-full bg-aura-border overflow-hidden"
        role="progressbar"
        aria-valuenow={completedCount}
        aria-valuemin={0}
        aria-valuemax={totalCount}
        aria-label="Habit completion progress"
      >
        <div
          className={[
            "h-full rounded-full transition-all duration-500",
            allDone
              ? "bg-aura-green shadow-aura-green"
              : "bg-gradient-to-r from-aura-purple to-aura-blue",
          ].join(" ")}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Habit list */}
      <div className="flex flex-col gap-2">
        {habits.length === 0 ? (
          <p className="text-xs text-aura-text-muted italic text-center py-2">
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
