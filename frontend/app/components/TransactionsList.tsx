import type { Transaction } from "../lib/api";
import { categoryColour, formatSignedEuro } from "../lib/format";
import { Card } from "./Card";

const dateFormat = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });

export function TransactionsList({
  transactions,
  monthLabel,
  flagged,
}: {
  transactions: Transaction[];
  monthLabel: string;
  flagged: Set<string>;
}) {
  return (
    <Card id="transactions" title="Transactions" subtitle={`${transactions.length} bookings in ${monthLabel}.`}>
      <ul className="-mx-5 divide-y divide-border border-t border-border sm:-mx-6">
        {transactions.map((t, index) => {
          const isIncome = t.amount > 0;
          const isFlagged = flagged.has(`${t.date}|${t.merchant}`);
          return (
            <li key={`${t.date}-${t.merchant}-${index}`} className="flex items-center gap-4 px-5 py-3 sm:px-6">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white"
                style={{ background: isIncome ? "var(--positive)" : categoryColour(t.category) }}
                aria-hidden
              >
                {t.merchant.charAt(0)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">
                  {t.merchant}
                  {isFlagged && (
                    <span className="ml-2 rounded-sm bg-warning-bg px-1.5 py-0.5 text-[11px] font-medium text-warning">
                      ⚠ Unusual
                    </span>
                  )}
                </p>
                <p className="text-sm text-ink-3">
                  {dateFormat.format(new Date(t.date))} · {t.category}
                </p>
              </div>
              <span className={`font-semibold tabular-nums ${isIncome ? "text-positive" : "text-ink"}`}>
                {formatSignedEuro(t.amount)}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
