"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MonthlySpending } from "../lib/api";
import { categoryColour, formatEuro, formatMonth } from "../lib/format";
import { Card, tooltipStyle } from "./Card";

export function SpendingChart({
  data,
  categories,
  fixedCategories,
  selectedMonth,
  selectedCategory,
  onSelect,
}: {
  data: MonthlySpending[];
  categories: string[];
  fixedCategories: string[];
  selectedMonth: string;
  selectedCategory: string;
  onSelect: (month: string, category: string) => void;
}) {
  const [showTable, setShowTable] = useState(false);
  // Fixed costs (rent, subscriptions) barely change and dwarf the rest, so they start hidden.
  const [includeFixed, setIncludeFixed] = useState(false);
  const visible = includeFixed ? categories : categories.filter((c) => !fixedCategories.includes(c));

  return (
    <Card
      title="Monthly spending by category"
      subtitle="Click a segment to see which merchants are behind it."
      action={
        <div className="flex items-center gap-3">
          {fixedCategories.length > 0 && (
            <label className="flex items-center gap-2 text-xs text-ink-2">
              <input
                type="checkbox"
                checked={includeFixed}
                onChange={(event) => setIncludeFixed(event.target.checked)}
                className="accent-brand"
              />
              Include fixed costs
            </label>
          )}
          <button
            type="button"
            onClick={() => setShowTable((value) => !value)}
            className="rounded border border-border px-3 py-1.5 text-xs font-medium text-ink-2 hover:bg-background"
          >
            {showTable ? "Show chart" : "Show table"}
          </button>
        </div>
      }
    >
      <ul className="mb-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-ink-2">
        {visible.map((category) => (
          <li key={category} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: categoryColour(category) }} />
            <span className={category === selectedCategory ? "font-medium text-ink" : ""}>{category}</span>
          </li>
        ))}
      </ul>

      {showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="border-b border-border text-left text-ink-3">
                <th className="py-2 pr-4 font-medium">Month</th>
                {visible.map((category) => (
                  <th key={category} className="py-2 pr-4 text-right font-medium">
                    {category}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.month} className="border-b border-border/60 text-ink-2">
                  <td className="py-2 pr-4 text-ink">{formatMonth(row.month)}</td>
                  {visible.map((category) => (
                    <td key={category} className="py-2 pr-4 text-right">
                      {formatEuro(Number(row[category] ?? 0))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          className="h-80"
          role="img"
          aria-label={`Stacked bar chart of monthly spending by category from ${formatMonth(data[0]?.month ?? "")} to ${formatMonth(data[data.length - 1]?.month ?? "")}. Use "Show table" for the exact values.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} barCategoryGap="28%">
              <CartesianGrid vertical={false} stroke="var(--grid)" />
              <XAxis
                dataKey="month"
                tickFormatter={(month) => formatMonth(month, false)}
                tick={{ fill: "var(--ink-3)", fontSize: 12 }}
                axisLine={{ stroke: "var(--border)" }}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(value) => `€${value}`}
                tick={{ fill: "var(--ink-3)", fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                width={48}
              />
              <Tooltip
                {...tooltipStyle}
                labelFormatter={(month) => formatMonth(String(month))}
                formatter={(value, name) => [formatEuro(Number(value)), name]}
              />
              {visible.map((category, index) => (
                <Bar
                  key={category}
                  dataKey={category}
                  name={category}
                  stackId="spend"
                  fill={categoryColour(category)}
                  stroke="var(--surface)"
                  strokeWidth={2}
                  radius={index === visible.length - 1 ? [4, 4, 0, 0] : 0}
                  cursor="pointer"
                  onClick={(bar) => bar.payload && onSelect(bar.payload.month, category)}
                  isAnimationActive={false}
                >
                  {/* Dim months other than the one being explored. */}
                  {data.map((row) => (
                    <Cell key={row.month} fillOpacity={row.month === selectedMonth ? 1 : 0.35} />
                  ))}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
