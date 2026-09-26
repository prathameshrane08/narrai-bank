const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
  type: "category_change" | "unusual_payment" | "new_merchant" | "weekend_pattern" | "savings_rate";
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
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return response.json();
}

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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, month, previous }),
  });
  if (!response.ok) {
    throw new Error(`Chat request failed with status ${response.status}`);
  }
  return response.json();
}
