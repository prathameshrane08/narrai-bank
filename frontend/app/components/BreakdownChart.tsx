"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MerchantSpending } from "../lib/api";
import { categoryColour, formatEuro, formatMonth, formatSignedEuro } from "../lib/format";
import { Card, tooltipStyle } from "./Card";

type Row = { merchant: string; current: number; previous: number };

function buildRows(breakdown: MerchantSpending[], category: string, month: string, previousMonth: string | null) {
  const rows = new Map<string, Row>();

  for (const item of breakdown) {
    if (item.category !== category) continue;
    if (item.month !== month && item.month !== previousMonth) continue;

    const row = rows.get(item.merchant) ?? { merchant: item.merchant, current: 0, previous: 0 };
    if (item.month === month) row.current += item.amount;
    else row.previous += item.amount;
    rows.set(item.merchant, row);
  }

  return [...rows.values()].sort((a, b) => b.current - a.current || b.previous - a.previous);
}

export function BreakdownChart({
  breakdown,
  categories,
  category,
  month,
  previousMonth,
  onCategoryChange,
}: {
  breakdown: MerchantSpending[];
  categories: string[];
  category: string;
  month: string;
  previousMonth: string | null;
  onCategoryChange: (category: string) => void;
}) {
  const rows = buildRows(breakdown, category, month, previousMonth);
  const colour = categoryColour(category);

  return (
    <Card
      title={`${category} by merchant`}
      subtitle={
        previousMonth
          ? `${formatMonth(month)} compared with ${formatMonth(previousMonth)}.`
          : `${formatMonth(month)}.`
      }
      action={
        <select
          value={category}
          onChange={(event) => onCategoryChange(event.target.value)}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-ink"
          aria-label="Category"
        >
          {categories.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      }
    >
      {rows.length === 0 ? (
        <p className="text-sm text-ink-3">No {category.toLowerCase()} spending in this period.</p>
      ) : (
        <>
          <ul className="mb-4 flex gap-5 text-sm text-ink-2">
            <li className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colour }} />
              {formatMonth(month)}
            </li>
            {previousMonth && (
              <li className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: colour, opacity: 0.35 }} />
                {formatMonth(previousMonth)}
              </li>
            )}
          </ul>

          <div style={{ height: Math.max(160, rows.length * 64) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} layout="vertical" barGap={2} barCategoryGap="24%">
                <CartesianGrid horizontal={false} stroke="var(--grid)" />
                <XAxis
                  type="number"
                  tickFormatter={(value) => `€${value}`}
                  tick={{ fill: "var(--ink-3)", fontSize: 12 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="merchant"
                  tick={{ fill: "var(--ink-2)", fontSize: 13 }}
                  axisLine={false}
                  tickLine={false}
                  width={90}
                />
                <Tooltip
                  {...tooltipStyle}
                  formatter={(value, name) => [formatEuro(Number(value)), name]}
                />
                <Bar
                  dataKey="current"
                  name={formatMonth(month)}
                  fill={colour}
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                />
                {previousMonth && (
                  <Bar
                    dataKey="previous"
                    name={formatMonth(previousMonth)}
                    fill={colour}
                    fillOpacity={0.35}
                    radius={[0, 4, 4, 0]}
                    isAnimationActive={false}
                  />
                )}
              </BarChart>
            </ResponsiveContainer>
          </div>

          {previousMonth && (
            <ul className="mt-4 divide-y divide-border border-t border-border text-sm tabular-nums">
              {rows.map((row) => (
                <li key={row.merchant} className="flex justify-between py-2">
                  <span className="text-ink">{row.merchant}</span>
                  <span className="text-ink-2">
                    {formatEuro(row.current)}{" "}
                    <span className="text-ink-3">({formatSignedEuro(row.current - row.previous)})</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}
