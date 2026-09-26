"use client";

import { useEffect, useState } from "react";

import { AccountOverview } from "./components/AccountOverview";
import { AppHeader } from "./components/AppHeader";
import { ChatAssistant } from "./components/ChatAssistant";
import { BudgetsPanel } from "./components/BudgetsPanel";
import { BreakdownChart } from "./components/BreakdownChart";
import { InsightFeed } from "./components/InsightFeed";
import { KpiTiles } from "./components/KpiTiles";
import { NextSteps } from "./components/NextSteps";
import { SpendingChart } from "./components/SpendingChart";
import { StoryCard } from "./components/StoryCard";
import { TransactionsList } from "./components/TransactionsList";
import {
  type Budgets,
  type Dashboard,
  type Story,
  type Tenant,
  fetchBudgets,
  fetchDashboard,
  fetchMonths,
  fetchStory,
  fetchTenant,
  fetchTenants,
  removeBudget,
  saveBudget,
  setTenantId,
} from "./lib/api";
import { formatMonth } from "./lib/format";
import { applyTenantTheme, tenantFromUrl } from "./lib/theme";

function BrandSwitcher({ tenant, tenants }: { tenant: Tenant; tenants: { id: string; bank_name: string }[] }) {
  if (tenants.length < 2) return null;
  return (
    <label className="flex items-center gap-2">
      Demo brand
      <select
        value={tenant.id}
        onChange={(event) => {
          window.location.search = `?bank=${event.target.value}`;
        }}
        className="rounded-sm border border-border bg-surface px-2 py-1 text-ink"
      >
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.bank_name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Shell({
  children,
  header,
  footer,
}: {
  children: React.ReactNode;
  header?: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <>
      {header}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-ink-3 sm:px-6">
          {footer}
        </div>
      </footer>
    </>
  );
}

export default function Home() {
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [tenants, setTenants] = useState<{ id: string; bank_name: string }[]>([]);
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [storyResult, setStoryResult] = useState<Story | null>(null);
  const [storyErrorMonth, setStoryErrorMonth] = useState<string | null>(null);

  const [budgets, setBudgets] = useState<Budgets | null>(null);
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const storyEnabled = tenant?.features.story !== false;

  // Drill-down selection: which bar segment the user is exploring.
  const [focus, setFocus] = useState<{ month: string; category: string } | null>(null);

  // Load the bank's white-label config first, so every later request carries its tenant header.
  useEffect(() => {
    const requested = tenantFromUrl();
    if (requested) setTenantId(requested);

    fetchTenants()
      .then((data) => setTenants(data.tenants))
      .catch(() => setTenants([]));

    fetchTenant()
      .then((config) => {
        applyTenantTheme(config);
        setTenant(config);
        return fetchMonths();
      })
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

    fetchBudgets(month)
      .then((data) => !cancelled && setBudgets(data))
      .catch(() => !cancelled && setBudgetError("Budgets could not be loaded."));

    if (storyEnabled) {
      fetchStory(month)
        .then((data) => !cancelled && setStoryResult(data))
        .catch(() => !cancelled && setStoryErrorMonth(month));
    }

    return () => {
      cancelled = true;
    };
  }, [month, storyEnabled]);

  // Save or remove a budget, then refresh the dashboard so the insight feed reflects it.
  async function changeBudget(action: () => Promise<Budgets>) {
    if (!month) return;
    setBudgetBusy(true);
    setBudgetError(null);
    try {
      setBudgets(await action());
      setDashboard(await fetchDashboard(month));
    } catch {
      setBudgetError("That budget change could not be saved. Please try again.");
    } finally {
      setBudgetBusy(false);
    }
  }

  if (error) {
    return (
      <Shell header={tenant && <AppHeader monthPicker={null} bankName={tenant.bank_name} logo={tenant.logo} />}>
        <p className="text-warning">{error}</p>
      </Shell>
    );
  }

  if (!dashboard || !month || !focus || !tenant) {
    return (
      <Shell header={tenant && <AppHeader monthPicker={null} bankName={tenant.bank_name} logo={tenant.logo} />}>
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
    <Shell
      header={<AppHeader monthPicker={monthPicker} bankName={tenant.bank_name} logo={tenant.logo} />}
      footer={
        <>
          <span>{tenant.legal_footer}</span>
          <BrandSwitcher tenant={tenant} tenants={tenants} />
        </>
      }
    >
      <p className="text-sm text-ink-3">Financial overview</p>
      <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink">{facts.month_label}</h1>

      <div className="mt-5 space-y-5">
        <AccountOverview account={dashboard.account} label={tenant.account_label} />

        {tenant.features.story !== false && (
          <StoryCard
            story={story}
            loading={!story && !storyError}
            error={storyError}
            monthLabel={facts.month_label}
            assistantName={tenant.assistant_name}
          />
        )}

        {tenant.features.insights !== false && (
          <InsightFeed
            insights={dashboard.insights}
            monthLabel={facts.month_label}
            onExplore={(insight) => {
              if (!insight.category) return;
              setFocus({ month: insight.month, category: insight.category });
              document.getElementById("spending")?.scrollIntoView({ behavior: "smooth" });
            }}
          />
        )}

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

        <BudgetsPanel
          data={budgets}
          categories={dashboard.categories}
          monthLabel={facts.month_label}
          busy={budgetBusy}
          error={budgetError}
          onSave={(category, amount) => changeBudget(() => saveBudget(category, amount, month))}
          onRemove={(category) => changeBudget(() => removeBudget(category, month))}
        />

        <div className="grid items-start gap-5 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <NextSteps
              recommendations={facts.recommendations}
              budgetedCategories={new Set(budgets?.budgets.map((b) => b.category))}
              onCreateBudget={(category, amount) => changeBudget(() => saveBudget(category, amount, month))}
            />
          </div>
          <div className="lg:col-span-3">
            <TransactionsList transactions={dashboard.transactions} monthLabel={facts.month_label} flagged={flagged} />
          </div>
        </div>
      </div>

      {tenant.features.chat !== false && <ChatAssistant month={month} assistantName={tenant.assistant_name} />}
    </Shell>
  );
}
