import type { Story, StorySectionName } from "../lib/api";

const QUESTIONS: { key: StorySectionName; question: string }[] = [
  { key: "what_happened", question: "What happened?" },
  { key: "why", question: "Why did it happen?" },
  { key: "meaning", question: "What does it mean?" },
  { key: "next_step", question: "What can I do next?" },
];

function SourceBadge({ source, issues }: { source: "ai" | "template"; issues: string[] }) {
  if (source === "ai") {
    return (
      <span
        className="rounded-sm bg-brand-soft px-1.5 py-0.5 text-[11px] font-medium text-brand"
        title="Written by the AI and checked against the verified facts"
      >
        AI · verified
      </span>
    );
  }
  return (
    <span
      className="rounded-sm bg-background px-1.5 py-0.5 text-[11px] font-medium text-ink-2"
      title={issues.length ? `AI draft rejected: ${issues.join(", ")}` : "Generated from verified facts"}
    >
      From facts
    </span>
  );
}

export function StoryCard({
  story,
  loading,
  error,
  monthLabel,
  assistantName,
  onRetry,
}: {
  story: Story | null;
  loading: boolean;
  error: string | null;
  monthLabel: string;
  assistantName: string;
  onRetry: () => void;
}) {
  return (
    <section id="insights" className="scroll-mt-24 rounded border border-border border-l-4 border-l-brand bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-sm bg-brand text-sm font-bold text-on-brand">
            AI
          </span>
          <div>
            <h2 className="text-base font-semibold text-ink">Your {monthLabel} in a nutshell</h2>
            <p className="text-sm text-ink-3">Numbers calculated by {assistantName}, explained in plain words.</p>
          </div>
        </div>
        {story && (
          <span className="text-xs text-ink-3">
            {story.ai_available ? `Narrated by ${story.model}` : "AI offline, showing verified summary"}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 px-5 pt-4 text-sm text-warning sm:px-6">
          <span>{error} The numbers below are unaffected.</span>
          <button type="button" onClick={onRetry} className="font-medium text-brand underline">
            Try again
          </button>
        </div>
      )}

      <ol className="grid md:grid-cols-2">
        {QUESTIONS.map(({ key, question }, index) => {
          const section = story?.sections[key];
          return (
            <li
              key={key}
              className={`px-5 py-5 sm:px-6 ${index % 2 === 0 ? "md:border-r" : ""} ${
                index < 2 ? "border-b" : index === 2 ? "border-b md:border-b-0" : ""
              } border-border`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold tabular-nums text-brand">0{index + 1}</span>
                <h3 className="text-sm font-semibold text-ink">{question}</h3>
                {section && <SourceBadge source={section.source} issues={section.issues} />}
              </div>
              {error && !section ? (
                <p className="mt-2 text-sm text-ink-3">Not available right now.</p>
              ) : loading || !section ? (
                <div className="mt-3 space-y-2" aria-label="Writing story">
                  <div className="h-3 w-full animate-pulse rounded-sm bg-ink-3/15" />
                  <div className="h-3 w-2/3 animate-pulse rounded-sm bg-ink-3/15" />
                </div>
              ) : (
                <p className="mt-2 text-[15px] leading-6 text-ink-2">{section.text}</p>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
