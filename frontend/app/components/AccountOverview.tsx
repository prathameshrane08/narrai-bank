import type { Account } from "../lib/api";
import { formatEuro, formatMonth, formatSignedEuro } from "../lib/format";

function Flow({ label, value, tone }: { label: string; value: string; tone?: "positive" }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-white/60">{label}</p>
      <p className={`mt-1 text-lg font-semibold tabular-nums ${tone === "positive" ? "text-emerald-300" : ""}`}>
        {value}
      </p>
    </div>
  );
}

export function AccountOverview({ account }: { account: Account }) {
  return (
    <section id="overview" className="scroll-mt-24 overflow-hidden rounded bg-brand-dark text-white">
      <div className="flex flex-wrap items-end justify-between gap-6 p-6 sm:p-8">
        <div>
          <p className="text-sm text-white/70">Current account · Demo</p>
          <p className="mt-1 font-mono text-sm tracking-wider text-white/60">DE•• •••• •••• •••• •••• 00</p>
          <p className="mt-6 text-sm text-white/70">Balance at end of {formatMonth(account.month)}</p>
          <p className="mt-1 text-4xl font-semibold tracking-tight tabular-nums sm:text-5xl">
            {formatEuro(account.balance)}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-6 sm:gap-10">
          <Flow label="Money in" value={formatSignedEuro(account.income)} tone="positive" />
          <Flow label="Money out" value={formatSignedEuro(-account.spending)} />
          <Flow label="Net" value={formatSignedEuro(account.net)} tone={account.net >= 0 ? "positive" : undefined} />
        </div>
      </div>
    </section>
  );
}
