import Image from "next/image";
import type { ReactNode } from "react";

const NAV = [
  { href: "#overview", label: "Overview" },
  { href: "#insights", label: "Insights" },
  { href: "#spending", label: "Spending" },
  { href: "#budgets", label: "Budgets" },
  { href: "#transactions", label: "Transactions" },
];

export function AppHeader({
  monthPicker,
  bankName,
  logo,
}: {
  monthPicker: ReactNode;
  bankName?: string;
  logo?: string;
}) {
  return (
    <header className="sticky top-0 z-20 bg-brand text-on-brand shadow-sm">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-4 sm:px-6">
        <a href="#overview" className="flex shrink-0 items-center gap-2.5">
          {/* The bank's own logo from its white-label config (local SVG, so no image optimisation needed). */}
          {logo && <Image src={logo} alt="" width={32} height={32} unoptimized priority />}
          <span className="whitespace-nowrap text-lg font-semibold tracking-tight">{bankName}</span>
        </a>

        {/* Show/hide lives on a plain wrapper so it can't be overridden by anything targeting .flex. */}
        <div className="max-md:[display:none]">
          <nav className="flex items-center gap-6 text-sm text-on-brand/80" aria-label="Sections">
            {NAV.map((item) => (
              <a key={item.href} href={item.href} className="py-5 hover:text-on-brand">
                {item.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="ml-auto flex items-center gap-4">
          {monthPicker}
          <span className="max-sm:[display:none]">
            <span
              className="flex h-9 w-9 items-center justify-center rounded-full bg-on-brand/15 text-sm font-medium"
              title="Demo customer"
            >
              DC
            </span>
          </span>
        </div>
      </div>
    </header>
  );
}
