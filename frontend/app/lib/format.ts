const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatMonth(month: string, withYear = true) {
  const [year, monthNumber] = month.split("-");
  const name = MONTHS[Number(monthNumber) - 1];
  return withYear ? `${name} ${year}` : name;
}

export function formatMonthLong(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  return new Date(year, monthNumber - 1, 1).toLocaleString("en-GB", { month: "long", year: "numeric" });
}

const euro = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });

export function formatEuro(value: number) {
  return euro.format(value);
}

export function formatSignedEuro(value: number) {
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${euro.format(Math.abs(value))}`;
}

export function formatSignedPct(value: number | null) {
  if (value === null) return "new";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(1)}%`;
}

// Categorical colours follow the entity, never its rank, so a category keeps
// its colour in every chart and month. Unknown categories fall back to neutral.
const CATEGORY_COLOURS: Record<string, string> = {
  Restaurant: "var(--cat-1)",
  Groceries: "var(--cat-2)",
  Transport: "var(--cat-3)",
  Shopping: "var(--cat-4)",
  Subscriptions: "var(--cat-5)",
  Entertainment: "var(--cat-6)",
  Health: "var(--cat-7)",
  Housing: "var(--cat-8)",
};

export function categoryColour(category: string) {
  return CATEGORY_COLOURS[category] ?? "var(--cat-other)";
}
