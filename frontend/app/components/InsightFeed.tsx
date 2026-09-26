import type { Insight } from "../lib/api";
import { Card } from "./Card";

const TYPE_LABELS: Record<Insight["type"], string> = {
  category_change: "Spending change",
  unusual_payment: "Unusual payment",
  new_merchant: "New merchant",
  weekend_pattern: "Pattern",
  savings_rate: "Income",
  budget: "Budget",
};

// Status is carried by an icon and a label as well as colour, never colour alone.
const TONES: Record<Insight["tone"], { icon: string; label: string; badge: string; bar: string }> = {
  warning: { icon: "⚠", label: "Needs attention", badge: "bg-warning-bg text-warning", bar: "bg-warning" },
  positive: { icon: "✓", label: "Good news", badge: "bg-positive/10 text-positive", bar: "bg-positive" },
  neutral: { icon: "•", label: "Good to know", badge: "bg-brand-soft text-brand", bar: "bg-brand" },
};

export function InsightFeed({
  insights,
  monthLabel,
  onExplore,
}: {
  insights: Insight[];
  monthLabel: string;
  onExplore: (insight: Insight) => void;
}) {
  return (
    <Card
      id="insight-feed"
      title="What else happened"
      subtitle={`The most important things in ${monthLabel}, ranked. Every number is calculated from your transactions.`}
    >
      {insights.length === 0 ? (
        <p className="text-sm text-ink-3">Nothing unusual this month.</p>
      ) : (
        <ul className="-mx-5 grid border-t border-border sm:-mx-6 md:grid-cols-2 lg:grid-cols-3">
          {insights.map((insight) => {
            const tone = TONES[insight.tone];
            return (
              <li
                key={insight.id}
                className="relative flex flex-col gap-2 border-b border-border px-5 py-4 sm:px-6 md:border-r"
              >
                <span className={`absolute inset-y-0 left-0 w-1 ${tone.bar}`} aria-hidden />
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`rounded-sm px-1.5 py-0.5 text-[11px] font-medium ${tone.badge}`}>
                    <span aria-hidden>{tone.icon} </span>
                    {tone.label}
                  </span>
                  <span className="text-xs text-ink-3">{TYPE_LABELS[insight.type]}</span>
                </div>
                <p className="font-semibold text-ink">{insight.title}</p>
                <p className="text-sm leading-6 text-ink-2">{insight.detail}</p>
                {insight.category && (
                  <button
                    type="button"
                    onClick={() => onExplore(insight)}
                    className="mt-auto self-start text-sm font-medium text-brand hover:underline"
                  >
                    Explore {insight.category.toLowerCase()} →
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
