import type { ReactNode } from "react";

const NAV = [
  { href: "#overview", label: "Overview" },
  { href: "#insights", label: "Insights" },
  { href: "#spending", label: "Spending" },
  { href: "#transactions", label: "Transactions" },
];

export function AppHeader({ monthPicker }: { monthPicker: ReactNode }) {
  return (
    <header className="sticky top-0 z-20 bg-brand text-white shadow-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-4 sm:px-6">
        <a href="#overview" className="flex items-center gap-2.5">
          {/* Generic mark: a square with a rising line, not tied to any real bank's logo. */}
          <span className="flex h-8 w-8 items-center justify-center rounded-sm border-2 border-white">
            <svg viewBox="0 0 16 16" className="h-4 w-4" aria-hidden>
              <path d="M2 13 L7 8 L9.5 10.5 L14 4" fill="none" stroke="currentColor" strokeWidth="2" />
            </svg>
          </span>
          <span className="text-lg font-semibold tracking-tight">NarrAI Bank</span>
        </a>

        <nav className="flex items-center gap-6 text-sm text-white/80 max-md:[display:none]">
          {NAV.map((item) => (
            <a key={item.href} href={item.href} className="py-5 hover:text-white">
              {item.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {monthPicker}
          <span
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-sm font-medium max-sm:[display:none]"
            title="Demo customer"
          >
            DC
          </span>
        </div>
      </div>
    </header>
  );
}
