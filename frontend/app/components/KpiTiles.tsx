import type { Facts } from "../lib/api";
import { formatEuro, formatSignedEuro, formatSignedPct } from "../lib/format";

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded border border-border bg-surface p-5">
      <p className="text-sm text-ink-3">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-ink tabular-nums sm:text-3xl">
        {value}
      </p>
      <p className="mt-1 text-sm text-ink-2 tabular-nums">{note}</p>
    </div>
  );
}

export function KpiTiles({ facts }: { facts: Facts }) {
  const { totals, headline, drivers, patterns } = facts;
  const top = drivers[0];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Tile
        label="Total spending"
        value={formatEuro(totals.current)}
        note={`${formatSignedPct(totals.change_pct)} vs ${facts.previous_month_label}`}
      />
      <Tile
        label={`${headline.category} spending`}
        value={formatEuro(headline.current)}
        note={`${formatSignedPct(headline.change_pct)} · biggest change this month`}
      />
      <Tile
        label="Biggest contributor"
        value={top ? top.merchant : "—"}
        note={top ? `${formatSignedEuro(top.change_amount)} vs last month` : "No change"}
      />
      <Tile
        label="Weekend share"
        value={`${patterns.weekend_share_pct.toFixed(1)}%`}
        note={`of ${headline.category.toLowerCase()} spending`}
      />
    </div>
  );
}
