"use client";

import { useEffect, useState } from "react";

import { AccountOverview } from "./components/AccountOverview";
import { AppHeader } from "./components/AppHeader";
import { ChatAssistant } from "./components/ChatAssistant";
import { BreakdownChart } from "./components/BreakdownChart";
import { InsightFeed } from "./components/InsightFeed";
import { KpiTiles } from "./components/KpiTiles";
import { NextSteps } from "./components/NextSteps";
import { SpendingChart } from "./components/SpendingChart";
import { StoryCard } from "./components/StoryCard";
import { TransactionsList } from "./components/TransactionsList";
import { type Dashboard, type Story, fetchDashboard, fetchMonths, fetchStory } from "./lib/api";
import { formatMonth } from "./lib/format";

function Shell({ children, header }: { children: React.ReactNode; header?: React.ReactNode }) {
  return (
    <>
      {header}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto max-w-6xl px-4 py-5 text-xs text-ink-3 sm:px-6">
          NarrAI Bank prototype · Demo data only, not a real bank account. Figures are calculated by code; the AI
          only narrates them.
        </div>
      </footer>
    </>
  );
}

export default function Home() {
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [storyResult, setStoryResult] = useState<Story | null>(null);
  const [storyErrorMonth, setStoryErrorMonth] = useState<string | null>(null);

  // Drill-down selection: which bar segment the user is exploring.
  const [focus, setFocus] = useState<{ month: string; category: string } | null>(null);

  useEffect(() => {
    fetchMonths()
      .then(({ months, latest }) => {
        setMonths(months);
        setMonth(latest);
      })
      .catch(() => setError("Could not reach the NarrAI API. Is the backend running on port 8000?"));
  }, []);

  // Facts load fast; the AI story loads separately so charts never wait for the LLM.
  useEffect(() => {
    if (!month) return;
    let cancelled = false;

    fetchDashboard(month)
      .then((data) => {
        if (cancelled) return;
        setDashboard(data);
        setFocus({ month: data.facts.month, category: data.facts.headline.category });
      })
      .catch(() => !cancelled && setError("Could not load your financial data."));

    fetchStory(month)
      .then((data) => !cancelled && setStoryResult(data))
      .catch(() => !cancelled && setStoryErrorMonth(month));

    return () => {
      cancelled = true;
    };
  }, [month]);

  if (error) {
    return (
      <Shell header={<AppHeader monthPicker={null} />}>
        <p className="text-warning">{error}</p>
      </Shell>
    );
  }

  if (!dashboard || !month || !focus) {
    return (
      <Shell header={<AppHeader monthPicker={null} />}>
        <p className="text-ink-3">Loading your finances…</p>
      </Shell>
    );
  }

  const { facts } = dashboard;
  // Only show a story (or its error) that belongs to the selected month.
  const story = storyResult?.month === month ? storyResult : null;
  const storyError = storyErrorMonth === month ? "The story could not be generated right now." : null;
  const monthIndex = dashboard.monthly_spending.findIndex((row) => row.month === focus.month);
  const focusPrevious = monthIndex > 0 ? dashboard.monthly_spending[monthIndex - 1].month : null;

  const flagged = new Set(facts.alerts.map((alert) => `${alert.date}|${alert.merchant}`));

  const monthPicker = (
    <select
      value={month}
      onChange={(event) => setMonth(event.target.value)}
      aria-label="Statement month"
      className="rounded-sm border border-white/30 bg-white/10 px-3 py-1.5 text-sm text-white hover:bg-white/15"
    >
      {months.map((m) => (
        <option key={m} value={m} className="text-ink">
          {formatMonth(m)}
        </option>
      ))}
    </select>
  );

  return (
    <Shell header={<AppHeader monthPicker={monthPicker} />}>
      <p className="text-sm text-ink-3">Financial overview</p>
      <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink">{facts.month_label}</h1>

      <div className="mt-5 space-y-5">
        <AccountOverview account={dashboard.account} />

        <StoryCard story={story} loading={!story && !storyError} error={storyError} monthLabel={facts.month_label} />

        <InsightFeed
          insights={dashboard.insights}
          monthLabel={facts.month_label}
          onExplore={(insight) => {
            if (!insight.category) return;
            setFocus({ month: insight.month, category: insight.category });
            document.getElementById("spending")?.scrollIntoView({ behavior: "smooth" });
          }}
        />

        <KpiTiles facts={facts} />

        <div id="spending" className="grid scroll-mt-24 gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <SpendingChart
              data={dashboard.monthly_spending}
              categories={dashboard.categories}
              fixedCategories={facts.fixed_categories}
              selectedMonth={focus.month}
              selectedCategory={focus.category}
              onSelect={(m, category) => setFocus({ month: m, category })}
            />
          </div>
          <div className="lg:col-span-2">
            <BreakdownChart
              breakdown={dashboard.merchant_breakdown}
              categories={dashboard.categories}
              category={focus.category}
              month={focus.month}
              previousMonth={focusPrevious}
              onCategoryChange={(category) => setFocus({ ...focus, category })}
            />
          </div>
        </div>

        <div className="grid items-start gap-5 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <NextSteps recommendations={facts.recommendations} />
          </div>
          <div className="lg:col-span-3">
            <TransactionsList transactions={dashboard.transactions} monthLabel={facts.month_label} flagged={flagged} />
          </div>
        </div>
      </div>

      <ChatAssistant month={month} />
    </Shell>
  );
}
