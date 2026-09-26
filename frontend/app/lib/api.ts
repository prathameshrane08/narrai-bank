const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// Which bank (white-label tenant) this app instance is serving; sent with every request.
let tenantId = process.env.NEXT_PUBLIC_TENANT ?? "narrai";

export function setTenantId(id: string) {
  tenantId = id;
}

// ---------------------------------------------------------------- session

/** Who is signed in. The session token itself stays in an httpOnly cookie the page can't read. */
export type Session = { tenant: string; customerName: string; expiresAt: string };

/** Thrown when the session is missing, invalid or expired (HTTP 401). */
export class SignedOutError extends Error {}

/** Thrown when the API asks us to slow down (HTTP 429). */
export class RateLimitedError extends Error {}

// Customer data goes through the web app's own server (/bff), which adds the session from the cookie.
const BFF = "/bff";
// Writes carry this header; the server refuses writes without it (cross-site request forgery protection).
const WRITE_HEADERS = { "Content-Type": "application/json", "X-NarrAI-CSRF": "1" };

async function parse<T>(response: Response, what: string): Promise<T> {
  if (response.status === 401) {
    throw new SignedOutError("Your session has ended. Please sign in again.");
  }
  if (response.status === 429) {
    const wait = response.headers.get("Retry-After");
    throw new RateLimitedError(
      `You're going a little fast. Please try again${wait ? ` in ${wait} seconds` : " shortly"}.`,
    );
  }
  if (!response.ok) {
    throw new Error(`${what} failed with status ${response.status}`);
  }
  return response.json();
}

/** The current session, or null when signed out. */
export async function fetchSession(): Promise<Session | null> {
  const body = await parse<{ signedIn: boolean } & Partial<Session>>(await fetch(`${BFF}/session`), "Session");
  return body.signedIn ? { tenant: body.tenant!, customerName: body.customerName!, expiresAt: body.expiresAt! } : null;
}

/** Sign out: the web app server revokes the session at the API and clears the cookie. */
export async function signOut() {
  await fetch(`${BFF}/session`, { method: "DELETE", headers: WRITE_HEADERS }).catch(() => undefined);
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
  month: string;
  /** Null for a month with no previous month to compare with (e.g. a newly imported customer). */
  facts: Facts | null;
  notice: string | null;
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

/** Public, credential-free API calls (branding, demo brand list). */
async function getPublic<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { headers: { "X-NarrAI-Tenant": tenantId } });
  return parse<T>(response, `Request to ${path}`);
}

/** Customer data, via the web app server with the session cookie. */
async function get<T>(path: string): Promise<T> {
  return parse<T>(await fetch(`${BFF}${path}`), `Request to ${path}`);
}

export const fetchTenant = () => getPublic<Tenant>("/api/tenant");

export const fetchTenants = () => getPublic<{ tenants: { id: string; bank_name: string }[] }>("/api/tenants");

export const fetchMonths = () =>
  get<{ months: string[]; comparable: string[]; latest: string }>("/months");

export const fetchDashboard = (month: string) =>
  get<Dashboard>(`/dashboard?month=${month}`);

export const fetchStory = (month: string) =>
  get<Story>(`/story?month=${month}`);

export const fetchChatSuggestions = () => get<{ suggestions: string[] }>("/chat/suggestions");

export async function askQuestion(question: string, month: string, previous: ChatPlan | null): Promise<ChatReply> {
  const response = await fetch(`${BFF}/chat`, {
    method: "POST",
    headers: WRITE_HEADERS,
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
  const response = await fetch(`${BFF}${path}`, {
    method,
    headers: WRITE_HEADERS,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parse<T>(response, `${method} ${path}`);
}

export const fetchBudgets = (month: string) => get<Budgets>(`/budgets?month=${month}`);

export const saveBudget = (category: string, amount: number, month: string) =>
  send<Budgets>("PUT", `/budgets/${encodeURIComponent(category)}?month=${month}`, { amount });

export const removeBudget = (category: string, month: string) =>
  send<Budgets>("DELETE", `/budgets/${encodeURIComponent(category)}?month=${month}`);

// ---------------------------------------------------------------- demo sign-in

export type DemoCustomer = { ref: string; name: string };

/** Demo customers offered by the API in demo mode; null when demo sign-in is switched off. */
export async function fetchDemoCustomers(): Promise<DemoCustomer[] | null> {
  const response = await fetch(`${API_URL}/api/demo/customers`, { headers: { "X-NarrAI-Tenant": tenantId } });
  if (response.status === 404) return null;
  return (await parse<{ customers: DemoCustomer[] }>(response, "Demo customers")).customers;
}

/** Demo sign-in: the web app server creates the session and keeps it in the httpOnly cookie. */
export async function demoSignIn(ref: string): Promise<Session> {
  const response = await fetch(`${BFF}/demo`, {
    method: "POST",
    headers: WRITE_HEADERS,
    body: JSON.stringify({ tenant: tenantId, customer_ref: ref }),
  });
  const body = await parse<Session>(response, "Demo sign-in");
  return { tenant: body.tenant, customerName: body.customerName, expiresAt: body.expiresAt };
}

/** The signed-in customer's own data (GDPR export), saved as a JSON file. */
export async function downloadMyData(): Promise<void> {
  const response = await fetch(`${BFF}/me/export`);
  if (!response.ok) await parse(response, "Data export");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "my-data.json";
  link.click();
  URL.revokeObjectURL(url);
}
