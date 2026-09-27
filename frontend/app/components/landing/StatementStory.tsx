"use client";

import { useState } from "react";

import styles from "../../landing.module.css";

// The sample account from the live demo (August 2026), so every figure here can be checked there too.
const STATEMENT = [
  { date: "2026-07-11", text: "KARTENZAHLUNG L'OSTERIA BERLIN//DE", amount: "-28,50", tags: ["july", "osteria-july"] },
  { date: "2026-07-18", text: "KARTENZAHLUNG DOMINOS PIZZA 0412", amount: "-22,00", tags: ["july"] },
  { date: "2026-08-08", text: "KARTENZAHLUNG L'OSTERIA BERLIN//DE", amount: "-39,50", tags: ["august", "osteria"] },
  { date: "2026-08-15", text: "KARTENZAHLUNG DOMINOS PIZZA 0412", amount: "-32,00", tags: ["august"] },
  { date: "2026-08-22", text: "SUMUP *VAPIANO FRIEDRICHSTR", amount: "-41,50", tags: ["august"] },
  { date: "2026-08-29", text: "KARTENZAHLUNG L'OSTERIA BERLIN//DE", amount: "-36,50", tags: ["august", "osteria"] },
];

type Figure = { id: string; shown: string; lines: string[]; calculation: string };

const FIGURES: Record<string, Figure> = {
  change: {
    id: "change",
    shown: "196%",
    lines: ["july", "august"],
    calculation: "(149.50 − 50.50) ÷ 50.50 = +196.0%",
  },
  total: {
    id: "total",
    shown: "€149.50",
    lines: ["august"],
    calculation: "39.50 + 32.00 + 41.50 + 36.50 = 149.50",
  },
  merchant: {
    id: "merchant",
    shown: "€47.50",
    lines: ["osteria", "osteria-july"],
    calculation: "L'Osteria: (39.50 + 36.50) − 28.50 = 47.50",
  },
};

function TracedNumber({ figure, active, onSelect }: { figure: Figure; active: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      type="button"
      className={`${styles.figure} ${active ? styles.figureActive : ""}`}
      onMouseEnter={() => onSelect(figure.id)}
      onFocus={() => onSelect(figure.id)}
      onClick={() => onSelect(figure.id)}
      aria-describedby="calculation"
    >
      {figure.shown}
      <span className={styles.tick} aria-hidden>
        ✓
      </span>
    </button>
  );
}

/** A statement excerpt, the sentence NarrAI writes from it, and the calculation behind each number. */
export function StatementStory() {
  const [selected, setSelected] = useState<string>("total");
  const figure = FIGURES[selected];

  return (
    <figure className={styles.artifact}>
      <div className={styles.statement} aria-label="Bank statement excerpt">
        <p className={styles.statementHead}>Current account, restaurant payments</p>
        <ol className={styles.statementLines}>
          {STATEMENT.map((line) => {
            const lit = figure.lines.some((tag) => line.tags.includes(tag));
            return (
              <li key={line.date} className={lit ? styles.lineLit : undefined}>
                <span>{line.date}</span>
                <span className={styles.lineText}>{line.text}</span>
                <span className={styles.lineAmount}>{line.amount}</span>
              </li>
            );
          })}
        </ol>
      </div>

      <blockquote className={styles.story}>
        <p>
          Your restaurant spending went up{" "}
          <TracedNumber figure={FIGURES.change} active={selected === "change"} onSelect={setSelected} /> to{" "}
          <TracedNumber figure={FIGURES.total} active={selected === "total"} onSelect={setSelected} /> in
          August. L&apos;Osteria added the most:{" "}
          <TracedNumber figure={FIGURES.merchant} active={selected === "merchant"} onSelect={setSelected} />{" "}
          more than in July.
        </p>
      </blockquote>

      <figcaption id="calculation" className={styles.calculation} aria-live="polite">
        <span className={styles.calculationMark} aria-hidden>
          ✓
        </span>
        <span>
          <span className={styles.calculationLabel}>Calculated by NarrAI&apos;s analytics, not by the AI</span>
          <code>{figure.calculation}</code>
        </span>
      </figcaption>
    </figure>
  );
}
