const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Which bank (white-label tenant) this app instance is serving; sent with every request.
let tenantId = process.env.NEXT_PUBLIC_TENANT ?? "narrai";

export function setTenantId(id: string) {
  tenantId = id;
}

// ---------------------------------------------------------------- session

export type Session = { token: string; expiresAt: string; customerName: string };

/** Thrown when the API says the session is missing, invalid or expired (HTTP 401). */
export class SignedOutError extends Error {}

let session: Session | null = null;

// Per browser tab, per bank. In production the bank's app hands NarrAI the session;
// this storage exists for the stand-alone demo.
const storageKey = () => `narrai.session.${tenantId}`;

export function restoreSession(): Session | null {
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey()) ?? "null") as Session | null;
    session = stored && new Date(stored.expiresAt) > new Date() ? stored : null;
  } catch {
    session = null;
  }
  return session;
}

function storeSession(value: Session | null) {
  session = value;
  try {
    if (value) sessionStorage.setItem(storageKey(), JSON.stringify(value));
    else sessionStorage.removeItem(storageKey());
  } catch {
    // Storage can be unavailable (private mode); the session then lasts until reload.
  }
}

export function signOut() {
  storeSession(null);
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return {
    "X-NarrAI-Tenant": tenantId,
    ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
    ...extra,
  };
}

async function parse<T>(response: Response, what: string): Promise<T> {
  if (response.status === 401) {
    storeSession(null);
    throw new SignedOutError("Your session has ended. Please sign in again.");
  }
  if (!response.ok) {
    throw new Error(`${what} failed with status ${response.status}`);
  }
  return response.json();
}

export type Tenant = {
  id: string;
  bank_name: string;
  assistant_name: string;
  tagline: string;
  logo: string;
  colours: { brand: string; brand_dark: string; brand_soft: string; on_brand: string };
  account_label: string;
  legal_footer: string;
  advice_contact: string;
  features: { story?: boolean; chat?: boolean; insights?: boolean };
};

export type CategoryChange = {
  category: string;
  current: number;
  previous: number;
  change_amount: number;
  change_pct: number | null;
};

export type Headline = CategoryChange & {
  direction: "increase" | "decrease";
  trailing_average: number;
  trailing_months: number;
};

export type Driver = {
  merchant: string;
  current: number;
  previous: number;
  change_amount: number;
};

export type Patterns = {
  transactions_current: number;
  transactions_previous: number;
  average_transaction_current: number;
  average_transaction_previous: number;
  weekend_share_pct: number;
  share_of_month_total_pct: number;
};

export type Alert = {
  date: string;
  merchant: string;
  category: string;
  amount: number;
  typical_amount: number;
  times_typical: number;
};

export type Recommendation = {
  type: "budget" | "merchant" | "pattern" | "savings" | "alert";
  category?: string;
  budget?: number;
  title: string;
  detail: string;
  amount: number | null;
};

export type Facts = {
  month: string;
  month_label: string;
  previous_month: string;
  previous_month_label: string;
  totals: Omit<CategoryChange, "category">;
  headline: Headline;
  drivers: Driver[];
  patterns: Patterns;
  alerts: Alert[];
  recommendations: Recommendation[];
  category_changes: CategoryChange[];
  fixed_categories: string[];
};

export type Insight = {
  id: string;
  type: "category_change" | "unusual_payment" | "new_merchant" | "weekend_pattern" | "savings_rate" | "budget";
  tone: "warning" | "positive" | "neutral";
  title: string;
  detail: string;
  category: string | null;
  amount: number;
  score: number;
  month: string;
};

export type MonthlySpending = { month: string } & Record<string, number | string>;

export type MerchantSpending = {
  month: string;
  category: string;
  merchant: string;
  amount: number;
  transactions: number;
};

export type Account = {
  month: string;
  opening_balance: number;
  balance: number;
  income: number;
  spending: number;
  net: number;
};

export type Transaction = {
  date: string;
  merchant: string;
  category: string;
  amount: number;
};

export type Dashboard = {
  facts: Facts;
  insights: Insight[];
  account: Account;
  transactions: Transaction[];
  categories: string[];
  monthly_spending: MonthlySpending[];
  merchant_breakdown: MerchantSpending[];
};

export type StorySectionName = "what_happened" | "why" | "meaning" | "next_step";

export type StorySection = {
  text: string;
  source: "ai" | "template";
  issues: string[];
};

export type Story = {
  month: string;
  sections: Record<StorySectionName, StorySection>;
  model: string;
  ai_available: boolean;
};

export type ChatPlan = {
  tool: string;
  category: string | null;
  merchant: string | null;
  month: string;
  compare_month: string | null;
  n: number;
};

export type ChatReply = {
  question: string;
  month: string;
  answer: string;
  source: "ai" | "template" | "policy";
  tool: string;
  plan: ChatPlan | null;
  facts: Record<string, string | number>;
  issues: string[];
  router: "ai" | "keywords" | "policy";
  suggestions: string[];
};

async function get<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`${API_URL}${path}`, { headers: headers() }), `Request to ${path}`);
}

export const fetchTenant = () => get<Tenant>("/api/tenant");

export const fetchTenants = () => get<{ tenants: { id: string; bank_name: string }[] }>("/api/tenants");

export const fetchMonths = () =>
  get<{ months: string[]; latest: string | null }>("/api/months");

export const fetchDashboard = (month: string) =>
  get<Dashboard>(`/api/dashboard?month=${month}`);

export const fetchStory = (month: string) =>
  get<Story>(`/api/story?month=${month}`);

export const fetchChatSuggestions = () => get<{ suggestions: string[] }>("/api/chat/suggestions");

export async function askQuestion(question: string, month: string, previous: ChatPlan | null): Promise<ChatReply> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify({ question, month, previous }),
  });
  return parse<ChatReply>(response, "Chat request");
}

export type BudgetProgress = {
  category: string;
  budget: number;
  spent: number;
  remaining: number;
  percent_used: number;
  status: "on_track" | "close" | "over";
  in_progress: boolean;
  projected: number | null;
  months_within_budget: number;
  months_checked: number;
};

export type Budgets = {
  month: string;
  budgets: BudgetProgress[];
  suggestions: { category: string; amount: number }[];
};

async function send<T>(method: "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: headers({ "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parse<T>(response, `${method} ${path}`);
}

export const fetchBudgets = (month: string) => get<Budgets>(`/api/budgets?month=${month}`);

export const saveBudget = (category: string, amount: number, month: string) =>
  send<Budgets>("PUT", `/api/budgets/${encodeURIComponent(category)}?month=${month}`, { amount });

export const removeBudget = (category: string, month: string) =>
  send<Budgets>("DELETE", `/api/budgets/${encodeURIComponent(category)}?month=${month}`);

// ---------------------------------------------------------------- demo sign-in

export type DemoCustomer = { ref: string; name: string };

/** Demo customers offered by the API in demo mode; null when demo sign-in is switched off. */
export async function fetchDemoCustomers(): Promise<DemoCustomer[] | null> {
  const response = await fetch(`${API_URL}/api/demo/customers`, { headers: headers() });
  if (response.status === 404) return null;
  return (await parse<{ customers: DemoCustomer[] }>(response, "Demo customers")).customers;
}

export async function demoSignIn(ref: string): Promise<Session> {
  const response = await fetch(`${API_URL}/api/demo/sessions`, {
    method: "POST",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify({ customer_ref: ref }),
  });
  const body = await parse<{ token: string; expires_at: string; customer: { name: string } }>(
    response,
    "Demo sign-in",
  );
  const value = { token: body.token, expiresAt: body.expires_at, customerName: body.customer.name };
  storeSession(value);
  return value;
}
