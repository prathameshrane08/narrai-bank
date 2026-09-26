import type { Recommendation } from "../lib/api";
import { formatEuro } from "../lib/format";
import { Card } from "./Card";

const LABELS: Record<Recommendation["type"], string> = {
  budget: "Budget",
  merchant: "Merchant",
  pattern: "Pattern",
  savings: "Savings",
  alert: "Unusual payment",
};

export function NextSteps({
  recommendations,
  budgetedCategories,
  onCreateBudget,
}: {
  recommendations: Recommendation[];
  budgetedCategories: Set<string>;
  onCreateBudget: (category: string, amount: number) => void;
}) {
  return (
    <Card title="What you can do next" subtitle="Suggestions calculated from your own spending history.">
      {recommendations.length === 0 ? (
        <p className="text-sm text-ink-3">Nothing stands out this month. Nice work.</p>
      ) : (
        <ul className="space-y-3">
          {recommendations.map((rec) => {
            const isAlert = rec.type === "alert";
            return (
              <li
                key={rec.title}
                className={`rounded border p-4 ${
                  isAlert ? "border-warning/40 bg-warning-bg" : "border-border"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p
                      className={`text-xs font-medium uppercase tracking-wide ${
                        isAlert ? "text-warning" : "text-ink-3"
                      }`}
                    >
                      {isAlert && <span aria-hidden>⚠ </span>}
                      {LABELS[rec.type]}
                    </p>
                    <p className="mt-1 font-medium text-ink">{rec.title}</p>
                    <p className="mt-1 text-sm leading-6 text-ink-2">{rec.detail}</p>
                    {rec.type === "budget" && rec.category && rec.budget && (
                      budgetedCategories.has(rec.category) ? (
                        <p className="mt-2 text-sm font-medium text-positive">✓ Budget set, see Budgets</p>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onCreateBudget(rec.category!, rec.budget!)}
                          className="mt-2 rounded-sm border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand-soft"
                        >
                          Create this budget
                        </button>
                      )
                    )}
                  </div>
                  {rec.amount !== null && !isAlert && (
                    <div className="shrink-0 text-right">
                      <p className="text-xs text-ink-3">Potential saving</p>
                      <p className="font-semibold text-positive tabular-nums">{formatEuro(rec.amount)}</p>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
