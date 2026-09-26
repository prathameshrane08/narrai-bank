"use client";

import { type FormEvent, useState } from "react";

import type { BudgetProgress, Budgets } from "../lib/api";
import { formatEuro } from "../lib/format";
import { Card } from "./Card";

// Status is shown by colour, icon and words together, never colour alone.
const STATUS = {
  on_track: { label: "On track", icon: "✓", bar: "bg-positive", text: "text-positive" },
  close: { label: "Close to limit", icon: "!", bar: "bg-warning", text: "text-warning" },
  over: { label: "Over budget", icon: "⚠", bar: "bg-critical", text: "text-critical" },
} as const;

function BudgetRow({
  item,
  busy,
  onSave,
  onRemove,
}: {
  item: BudgetProgress;
  busy: boolean;
  onSave: (category: string, amount: number) => void;
  onRemove: (category: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(String(item.budget));
  const status = STATUS[item.status];
  const fill = Math.min(item.percent_used, 100);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = Number(amount);
    if (value > 0) {
      onSave(item.category, value);
      setEditing(false);
    }
  }

  return (
    <li className="py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-semibold text-ink">{item.category}</span>
          <span className={`text-xs font-medium ${status.text}`}>
            <span aria-hidden>{status.icon} </span>
            {status.label}
          </span>
        </div>
        <span className="text-sm tabular-nums text-ink-2">
          <span className="font-semibold text-ink">{formatEuro(item.spent)}</span> of {formatEuro(item.budget)}
        </span>
      </div>

      <div
        className="mt-2 h-2.5 overflow-hidden rounded-full bg-background"
        role="meter"
        aria-label={`${item.category} budget used`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fill)}
        aria-valuetext={`${item.percent_used}% used, ${status.label}`}
      >
        <div className={`h-full rounded-full ${status.bar}`} style={{ width: `${fill}%` }} />
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-3">
        <span className="tabular-nums">
          {item.remaining >= 0
            ? `${formatEuro(item.remaining)} left (${item.percent_used.toFixed(1)}% used)`
            : `${formatEuro(Math.abs(item.remaining))} over (${item.percent_used.toFixed(1)}% used)`}
          {item.projected !== null && ` · on pace for ${formatEuro(item.projected)}`}
          {item.months_checked > 0 &&
            ` · within budget ${item.months_within_budget} of the last ${item.months_checked} months`}
        </span>

        {editing ? (
          <form onSubmit={submit} className="flex items-center gap-2">
            <label className="sr-only" htmlFor={`budget-${item.category}`}>
              New {item.category} budget
            </label>
            <input
              id={`budget-${item.category}`}
              type="number"
              min={1}
              step={5}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="w-24 rounded-sm border border-border px-2 py-1 text-sm text-ink"
            />
            <button type="submit" disabled={busy} className="font-medium text-brand hover:underline">
              Save
            </button>
            <button type="button" onClick={() => setEditing(false)} className="hover:underline">
              Cancel
            </button>
          </form>
        ) : (
          <span className="flex gap-3">
            <button type="button" onClick={() => setEditing(true)} className="font-medium text-brand hover:underline">
              Edit
            </button>
            <button
              type="button"
              onClick={() => onRemove(item.category)}
              disabled={busy}
              className="hover:text-critical hover:underline"
            >
              Remove
            </button>
          </span>
        )}
      </div>
    </li>
  );
}

export function BudgetsPanel({
  data,
  categories,
  monthLabel,
  busy,
  error,
  onSave,
  onRemove,
}: {
  data: Budgets | null;
  categories: string[];
  monthLabel: string;
  busy: boolean;
  error: string | null;
  onSave: (category: string, amount: number) => void;
  onRemove: (category: string) => void;
}) {
  const withBudget = new Set(data?.budgets.map((b) => b.category));
  const available = categories.filter((c) => !withBudget.has(c));
  const suggested = new Map(data?.suggestions.map((s) => [s.category, s.amount]));

  const [category, setCategory] = useState("");
  const [amount, setAmount] = useState("");
  const selected = available.includes(category) ? category : (data?.suggestions[0]?.category ?? available[0] ?? "");

  function add(event: FormEvent) {
    event.preventDefault();
    const value = Number(amount || suggested.get(selected) || 0);
    if (selected && value > 0) {
      onSave(selected, value);
      setCategory("");
      setAmount("");
    }
  }

  return (
    <Card
      id="budgets"
      title="Budgets"
      subtitle={`Monthly limits you set, tracked against your ${monthLabel} spending.`}
    >
      {error && <p className="mb-3 text-sm text-critical">{error}</p>}

      {!data ? (
        <p className="text-sm text-ink-3">Loading budgets…</p>
      ) : (
        <>
          {data.budgets.length === 0 ? (
            <p className="text-sm text-ink-3">
              No budgets yet. Add one below; the suggested amounts come from your typical spending.
            </p>
          ) : (
            <ul className="-mt-4 divide-y divide-border">
              {data.budgets.map((item) => (
                <BudgetRow key={item.category} item={item} busy={busy} onSave={onSave} onRemove={onRemove} />
              ))}
            </ul>
          )}

          {available.length > 0 && (
            <form onSubmit={add} className="mt-4 flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <label className="flex flex-col gap-1 text-xs text-ink-3">
                Category
                <select
                  value={selected}
                  onChange={(event) => {
                    setCategory(event.target.value);
                    setAmount("");
                  }}
                  className="rounded-sm border border-border bg-surface px-2 py-1.5 text-sm text-ink"
                >
                  {available.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-ink-3">
                Monthly limit (€)
                <input
                  type="number"
                  min={1}
                  step={5}
                  placeholder={suggested.has(selected) ? String(suggested.get(selected)) : "e.g. 100"}
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                  className="w-32 rounded-sm border border-border px-2 py-1.5 text-sm text-ink"
                />
              </label>
              <button
                type="submit"
                disabled={busy || !(Number(amount) > 0 || suggested.has(selected))}
                className="rounded-sm bg-brand px-4 py-2 text-sm font-semibold text-on-brand hover:bg-brand-dark disabled:opacity-50"
              >
                Add budget
              </button>
              {suggested.has(selected) && !amount && (
                <span className="pb-2 text-xs text-ink-3">
                  Suggested {formatEuro(suggested.get(selected)!)} from your typical spending
                </span>
              )}
            </form>
          )}
        </>
      )}
    </Card>
  );
}
