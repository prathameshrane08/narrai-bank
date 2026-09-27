import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import Link from "next/link";

import { StatementStory } from "./components/landing/StatementStory";
import styles from "./landing.module.css";

const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-sans" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "NarrAI for banks",
  description:
    "Plain-language explanations of a customer's money for banking apps. Numbers are calculated; the AI only puts them into words, and a guardrail checks every sentence.",
};

const CONTACT = process.env.NEXT_PUBLIC_CONTACT_EMAIL;

const QUESTIONS = [
  { question: "What happened?", answer: "Restaurant spending went up 196% to €149.50." },
  { question: "Why?", answer: "L'Osteria added the most: €47.50 more than in July." },
  { question: "What does it mean?", answer: "All of it was spent on weekends." },
  { question: "What can I do?", answer: "A €50 monthly budget matches your usual spending; it would have saved €99.50." },
];

const STEPS = [
  {
    title: "Statements come in",
    text: "The bank sends camt.053, MT940 or CSV statements. Messy text such as “PAYPAL *ZALANDO 1043//BERLIN” becomes Zalando, Shopping.",
  },
  {
    title: "Analytics calculate",
    text: "Totals, changes, patterns, unusual payments and budget suggestions are computed in code. No model is involved.",
  },
  {
    title: "The model writes",
    text: "A language model running on the bank's own servers turns the verified facts into short sentences.",
  },
  {
    title: "The guardrail checks",
    text: "Every number, direction and topic in a sentence must match the facts. Anything that doesn't is replaced.",
  },
  {
    title: "The customer reads it",
    text: "Each sentence is marked as written by the AI and verified, or as a fixed sentence built from the facts.",
  },
];

const EVIDENCE = [
  { check: "Unverified numbers shown to customers", result: "0", detail: "in 216 story sentences and 30 chat answers" },
  {
    check: "Story sentences correct on a line-by-line review",
    result: "214 of 216",
    detail: "the 2 wrong ones are now caught by an added check",
  },
  { check: "Chat questions routed to the right calculation", result: "30 of 30", detail: "labelled test questions" },
  { check: "Investment, credit and off-topic questions declined", result: "6 of 6", detail: "before any model runs" },
  { check: "Statement lines categorised correctly", result: "60 of 60", detail: "labelled German statement lines" },
];

const BRANDS = [
  { id: "kestrel", name: "Kestrel Bank", colour: "#0b6e4f" },
  { id: "aurelia", name: "Aurelia Privatbank", colour: "#6b2d8c" },
  { id: "narrai", name: "NarrAI Bank", colour: "#0018a8" },
];

export default function Landing() {
  return (
    <div className={`${styles.page} ${plexSans.variable} ${plexMono.variable}`}>
      <a href="#main" className={styles.skip}>
        Skip to content
      </a>

      <header className={styles.header}>
        <span className={styles.wordmark}>NarrAI</span>
        <nav aria-label="Sections" className={styles.nav}>
          <a href="#how">How it works</a>
          <a href="#evidence">Evidence</a>
          <a href="#banks">For banks</a>
        </nav>
        <Link href="/app" className={styles.buttonSmall}>
          Open the live demo
        </Link>
      </header>

      <main id="main">
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroText}>
            <h1 id="hero-title">Your customers get the story. Every number stays checkable.</h1>
            <p className={styles.lead}>
              NarrAI turns a bank customer&apos;s transactions into short, plain-language explanations of what happened
              with their money and what to do next. The numbers come from calculations. The language model only puts
              them into words, and anything it writes that the calculations don&apos;t support is replaced before a
              customer sees it.
            </p>
            <div className={styles.actions}>
              <Link href="/app" className={styles.button}>
                Open the live demo
              </Link>
              <a href="#how" className={styles.textLink}>
                See how it works
              </a>
            </div>
          </div>
          <div className={styles.heroArtifact}>
            <StatementStory />
            <p className={styles.hint}>Point at a number, or tab to it, to see where it comes from.</p>
          </div>
        </section>

        <section className={styles.section} aria-labelledby="questions-title">
          <h2 id="questions-title">Four questions, answered every month</h2>
          <p className={styles.sectionLead}>
            Banking apps show balances, charts and long transaction lists, yet customers still can&apos;t tell what
            changed. NarrAI answers four questions, in the order people ask them.
          </p>
          <ol className={styles.questions}>
            {QUESTIONS.map((item) => (
              <li key={item.question}>
                <h3>{item.question}</h3>
                <p>{item.answer}</p>
              </li>
            ))}
          </ol>
          <p className={styles.aside}>
            Around the story: ranked insights, budgets with progress, alerts for unusual payments, and a chat that
            answers questions about the customer&apos;s own money.
          </p>
        </section>

        <section id="how" className={styles.section} aria-labelledby="how-title">
          <h2 id="how-title">How a sentence reaches a customer</h2>
          <div className={styles.howGrid}>
            <ol className={styles.steps}>
              {STEPS.map((step) => (
                <li key={step.title}>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </li>
              ))}
            </ol>
            <div className={styles.rejected} aria-label="Example of a rejected AI draft">
              <p className={styles.rejectedLabel}>AI draft</p>
              <p className={styles.draft}>
                <del>Your restaurant spending went up 210% to €149.50.</del>
              </p>
              <p className={styles.correction}>Rejected: 210% is not in the verified facts.</p>
              <p className={styles.rejectedLabel}>Shown to the customer instead</p>
              <p className={styles.shown}>Your restaurant spending increased by 196.0% in August 2026, reaching €149.50.</p>
            </div>
          </div>
        </section>

        <section id="evidence" className={styles.section} aria-labelledby="evidence-title">
          <h2 id="evidence-title">What the evaluation found</h2>
          <table className={styles.ledger}>
            <caption className={styles.visuallyHidden}>Evaluation results</caption>
            <thead>
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {EVIDENCE.map((row) => (
                <tr key={row.check}>
                  <th scope="row">
                    {row.check}
                    <span>{row.detail}</span>
                  </th>
                  <td>{row.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className={styles.aside}>
            Measured on synthetic customers with a small open model on a laptop. A pilot repeats the evaluation on the
            bank&apos;s own anonymised statements before anything reaches a customer.
          </p>
        </section>

        <section id="banks" className={styles.section} aria-labelledby="banks-title">
          <h2 id="banks-title">Built to sit inside a bank</h2>
          <dl className={styles.facts}>
            <div>
              <dt>Your brand</dt>
              <dd>
                One configuration file per bank sets the name, logo, colours and wording, checked for readable contrast.
                Try the same product in three fictional brands:
                <span className={styles.brands}>
                  {BRANDS.map((brand) => (
                    <Link key={brand.id} href={`/app?bank=${brand.id}`} className={styles.brand}>
                      <span className={styles.swatch} style={{ background: brand.colour }} aria-hidden />
                      {brand.name}
                    </Link>
                  ))}
                </span>
              </dd>
            </div>
            <div>
              <dt>Data stays where you decide</dt>
              <dd>
                The language model runs on your own servers by default, or on an EU-hosted model you choose. Customers
                can download their data, and the bank can erase it on request. The audit log keeps no names or amounts.
              </dd>
            </div>
            <div>
              <dt>Fits your stack</dt>
              <dd>
                A REST API with bank keys, statement import for camt.053, MT940 and CSV, and one-time links that open the
                white-label app with the customer already signed in. Or build the screens yourself on the API.
              </dd>
            </div>
            <div>
              <dt>Advice stays with your advisers</dt>
              <dd>
                Questions about investments, credit or loans are declined by a fixed rule and referred to the
                bank&apos;s own advisers.
              </dd>
            </div>
          </dl>
        </section>

        <section className={styles.closing} aria-labelledby="closing-title">
          <h2 id="closing-title">See it with your own clicks</h2>
          <p>Sign in as a demo customer and ask the chat about their spending. Nothing to install.</p>
          <div className={styles.actions}>
            <Link href="/app" className={styles.button}>
              Open the live demo
            </Link>
            {CONTACT && (
              <a href={`mailto:${CONTACT}`} className={styles.textLink}>
                Talk to us about a pilot
              </a>
            )}
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <p>NarrAI prototype. The demo uses synthetic data, and the banks shown in it are fictional.</p>
      </footer>
    </div>
  );
}
