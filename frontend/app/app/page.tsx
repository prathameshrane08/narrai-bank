"use client";

import { useCallback, useEffect, useState } from "react";

import { AccountOverview } from "../components/AccountOverview";
import { AppHeader } from "../components/AppHeader";
import { ChatAssistant } from "../components/ChatAssistant";
import { BudgetsPanel } from "../components/BudgetsPanel";
import { BreakdownChart } from "../components/BreakdownChart";
import { InsightFeed } from "../components/InsightFeed";
import { KpiTiles } from "../components/KpiTiles";
import { NextSteps } from "../components/NextSteps";
import { SignIn } from "../components/SignIn";
import { ErrorState, LoadingSkeleton } from "../components/StateScreens";
import { SpendingChart } from "../components/SpendingChart";
import { StoryCard } from "../components/StoryCard";
import { TransactionsList } from "../components/TransactionsList";
import {
  type Budgets,
  type Dashboard,
  type Session,
  type Story,
  type Tenant,
  SignedOutError,
  fetchBudgets,
  fetchDashboard,
  fetchMonths,
  fetchStory,
  fetchTenant,
  fetchTenants,
  removeBudget,
  fetchSession,
  downloadMyData,
  saveBudget,
  setTenantId,
  signOut,
} from "../lib/api";
import { formatMonth, formatMonthLong } from "../lib/format";
import { applyTenantTheme, tenantFromUrl } from "../lib/theme";

function BrandSwitcher({ tenant, tenants }: { tenant: Tenant; tenants: { id: string; bank_name: string }[] }) {
  // A session belongs to one bank, so switching the demo brand signs out first.
  if (tenants.length < 2) return null;
  return (
    <label className="flex items-center gap-2">
      Demo brand
      <select
        value={tenant.id}
        onChange={(event) => {
          const target = event.target.value;
          void signOut().then(() => {
            window.location.search = `?bank=${target}`;
          });
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
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-sm focus:bg-surface focus:px-4 focus:py-2 focus:text-ink focus:shadow"
      >
        Skip to main content
      </a>
      {header}
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {children}
      </main>
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
  // Months that have a previous month to compare with; only these get a story and insights.
  const [comparable, setComparable] = useState<string[]>([]);
  const [month, setMonth] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped by "Try again" to re-run the loaders.
  const [attempt, setAttempt] = useState(0);
  // undefined = not checked yet; null = signed out.
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [signInNotice, setSignInNotice] = useState<string | null>(null);
  const [storyAttempt, setStoryAttempt] = useState(0);

  const [storyResult, setStoryResult] = useState<Story | null>(null);
  const [storyErrorMonth, setStoryErrorMonth] = useState<string | null>(null);

  const [budgets, setBudgets] = useState<Budgets | null>(null);
  const [budgetBusy, setBudgetBusy] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const storyEnabled = tenant?.features.story !== false;

  // Drill-down selection: which bar segment the user is exploring.
  const [focus, setFocus] = useState<{ month: string; category: string } | null>(null);

  // Clear everything that belongs to the signed-in customer.
  const endSession = useCallback((notice: string | null) => {
    void signOut();
    setSession(null);
    setSignInNotice(notice);
    setMonth(null);
    setMonths([]);
    setDashboard(null);
    setBudgets(null);
    setStoryResult(null);
    setFocus(null);
  }, []);

  const handleFailure = useCallback(
    (err: unknown, message = "The banking service didn't respond. Please try again.") => {
      if (err instanceof SignedOutError) endSession(err.message);
      else setError(message);
    },
    [endSession],
  );

  // A signed-in customer's bank decides the branding; otherwise ?bank= (demo) or the default.
  useEffect(() => {
    async function load() {
      const current = await fetchSession();
      const requested = tenantFromUrl();
      setTenantId(current?.tenant ?? requested ?? process.env.NEXT_PUBLIC_TENANT ?? "narrai");

      fetchTenants()
        .then((data) => setTenants(data.tenants))
        .catch(() => setTenants([]));

      const config = await fetchTenant();
      applyTenantTheme(config);
      setTenant(config);
      setSession(current);
      const launch = new URLSearchParams(window.location.search).get("launch");
      if (!current && launch) {
        setSignInNotice(
          `This link has expired or was already used. Please open ${config.assistant_name} again from your banking app.`,
        );
      }
    }
    load().catch((err) => {
      console.warn("Could not reach the NarrAI API (is the backend running on port 8000?)", err);
      setError("The banking service didn't respond. Please check your connection and try again.");
    });
  }, [attempt]);

  // Once signed in, find which months this customer has data for.
  useEffect(() => {
    if (!session) return;
    fetchMonths()
      .then(({ months, comparable, latest }) => {
        setMonths(months);
        setComparable(comparable);
        setMonth(latest);
      })
      .catch((err) => handleFailure(err));
  }, [session, attempt, handleFailure]);

  // Facts load fast; the AI story loads separately so charts never wait for the LLM.
  useEffect(() => {
    if (!month) return;
    let cancelled = false;

    fetchDashboard(month)
      .then((data) => {
        if (cancelled) return;
        setDashboard(data);
        setFocus({ month: data.month, category: data.facts?.headline.category ?? data.categories[0] ?? "" });
      })
      .catch((err) => !cancelled && handleFailure(err, "Your account data couldn't be loaded."));

    fetchBudgets(month)
      .then((data) => !cancelled && setBudgets(data))
      .catch((err) =>
        !cancelled && (err instanceof SignedOutError ? handleFailure(err) : setBudgetError("Budgets could not be loaded.")),
      );

    return () => {
      cancelled = true;
    };
  }, [month, attempt, handleFailure]);

  // The story has its own loader so it can be retried without reloading the page.
  useEffect(() => {
    if (!month || !storyEnabled || !comparable.includes(month)) return;
    let cancelled = false;
    fetchStory(month)
      .then((data) => !cancelled && setStoryResult(data))
      .catch(() => !cancelled && setStoryErrorMonth(month));
    return () => {
      cancelled = true;
    };
  }, [month, storyEnabled, storyAttempt, comparable]);

  function retry() {
    setError(null);
    setAttempt((n) => n + 1);
  }

  function onSignedIn(value: Session) {
    setSignInNotice(null);
    setSession(value);
  }

  function retryStory() {
    setStoryErrorMonth(null);
    setStoryAttempt((n) => n + 1);
  }

  // Save or remove a budget, then refresh the dashboard so the insight feed reflects it.
  async function changeBudget(action: () => Promise<Budgets>) {
    if (!month) return;
    setBudgetBusy(true);
    setBudgetError(null);
    try {
      setBudgets(await action());
      setDashboard(await fetchDashboard(month));
    } catch (err) {
      if (err instanceof SignedOutError) endSession(err.message);
      else setBudgetError("That budget change could not be saved. Please try again.");
    } finally {
      setBudgetBusy(false);
    }
  }

  if (error) {
    return (
      <Shell header={tenant && <AppHeader monthPicker={null} bankName={tenant.bank_name} logo={tenant.logo} />}>
        <ErrorState message={error} onRetry={retry} />
      </Shell>
    );
  }

  if (tenant && session === null) {
    return (
      <Shell
        header={<AppHeader monthPicker={null} bankName={tenant.bank_name} logo={tenant.logo} />}
        footer={
          <>
            <span>{tenant.legal_footer}</span>
            <BrandSwitcher tenant={tenant} tenants={tenants} />
          </>
        }
      >
        <SignIn tenant={tenant} notice={signInNotice} onSignedIn={onSignedIn} />
      </Shell>
    );
  }

  if (!dashboard || !month || !focus || !tenant || !session) {
    return (
      <Shell header={tenant && <AppHeader monthPicker={null} bankName={tenant.bank_name} logo={tenant.logo} />}>
        <LoadingSkeleton />
      </Shell>
    );
  }

  const { facts } = dashboard;
  const monthLabel = facts?.month_label ?? formatMonthLong(month);
  // Only show a story (or its error) that belongs to the selected month.
  const story = storyResult?.month === month ? storyResult : null;
  const storyError = storyErrorMonth === month ? "The story could not be generated right now." : null;
  const monthIndex = dashboard.monthly_spending.findIndex((row) => row.month === focus.month);
  const focusPrevious = monthIndex > 0 ? dashboard.monthly_spending[monthIndex - 1].month : null;

  const flagged = new Set((facts?.alerts ?? []).map((alert) => `${alert.date}|${alert.merchant}`));

  const monthPicker = (
    <select
      value={month}
      onChange={(event) => setMonth(event.target.value)}
      aria-label="Statement month"
      className="rounded-sm border border-on-brand/30 bg-on-brand/10 px-3 py-1.5 text-sm text-on-brand hover:bg-on-brand/15"
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
      header={
        <AppHeader
          monthPicker={monthPicker}
          bankName={tenant.bank_name}
          logo={tenant.logo}
          customerName={session.customerName}
          onSignOut={() => endSession(null)}
          onDownloadData={() => downloadMyData().catch((err) => handleFailure(err, "Your data couldn't be downloaded."))}
        />
      }
      footer={
        <>
          <span>{tenant.legal_footer}</span>
          <BrandSwitcher tenant={tenant} tenants={tenants} />
        </>
      }
    >
      <p className="text-sm text-ink-3">Financial overview</p>
      <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink">{monthLabel}</h1>

      <div className="mt-5 space-y-5">
        <AccountOverview account={dashboard.account} label={tenant.account_label} />

        {!facts && dashboard.notice && (
          <p role="status" className="rounded border border-border bg-surface px-5 py-4 text-sm text-ink-2">
            {dashboard.notice}
          </p>
        )}

        {facts && tenant.features.story !== false && (
          <StoryCard
            story={story}
            loading={!story && !storyError}
            error={storyError}
            monthLabel={monthLabel}
            assistantName={tenant.assistant_name}
            onRetry={retryStory}
          />
        )}

        {facts && tenant.features.insights !== false && (
          <InsightFeed
            insights={dashboard.insights}
            monthLabel={monthLabel}
            onExplore={(insight) => {
              if (!insight.category) return;
              setFocus({ month: insight.month, category: insight.category });
              document.getElementById("spending")?.scrollIntoView({ behavior: "smooth" });
            }}
          />
        )}

        {facts && <KpiTiles facts={facts} />}

        <div id="spending" className="grid scroll-mt-24 gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <SpendingChart
              data={dashboard.monthly_spending}
              categories={dashboard.categories}
              fixedCategories={facts?.fixed_categories ?? []}
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
          monthLabel={monthLabel}
          busy={budgetBusy}
          error={budgetError}
          onSave={(category, amount) => changeBudget(() => saveBudget(category, amount, month))}
          onRemove={(category) => changeBudget(() => removeBudget(category, month))}
        />

        <div className="grid items-start gap-5 lg:grid-cols-5">
          {facts && (
            <div className="lg:col-span-2">
              <NextSteps
                recommendations={facts.recommendations}
                budgetedCategories={new Set(budgets?.budgets.map((b) => b.category))}
                onCreateBudget={(category, amount) => changeBudget(() => saveBudget(category, amount, month))}
              />
            </div>
          )}
          <div className={facts ? "lg:col-span-3" : "lg:col-span-5"}>
            <TransactionsList transactions={dashboard.transactions} monthLabel={monthLabel} flagged={flagged} />
          </div>
        </div>
      </div>

      {tenant.features.chat !== false && <ChatAssistant month={month} assistantName={tenant.assistant_name} />}
    </Shell>
  );
}
