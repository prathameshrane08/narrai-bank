"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { type ChatReply, askQuestion, fetchChatSuggestions } from "../lib/api";
import { formatMonth } from "../lib/format";

type Message = { role: "user"; text: string } | { role: "assistant"; reply: ChatReply } | { role: "error"; text: string };

const SOURCE_BADGES: Record<ChatReply["source"], { label: string; className: string; title: string }> = {
  ai: {
    label: "AI · verified",
    className: "bg-brand-soft text-brand",
    title: "Worded by the AI; every number was checked against the calculation",
  },
  template: {
    label: "From facts",
    className: "bg-background text-ink-2",
    title: "Written directly from the calculation",
  },
  policy: {
    label: "NarrAI policy",
    className: "bg-background text-ink-2",
    title: "Answered by a fixed rule, without AI",
  },
};

function AssistantMessage({ reply }: { reply: ChatReply }) {
  const [showNumbers, setShowNumbers] = useState(false);
  const badge = SOURCE_BADGES[reply.source];
  const facts = Object.entries(reply.facts);

  return (
    <div className="rounded border border-border bg-surface p-3">
      <p className="text-[15px] leading-6 text-ink">{reply.answer}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className={`rounded-sm px-1.5 py-0.5 text-[11px] font-medium ${badge.className}`} title={badge.title}>
          {badge.label}
        </span>
        {facts.length > 0 && (
          <button
            type="button"
            onClick={() => setShowNumbers((value) => !value)}
            className="text-xs font-medium text-brand hover:underline"
            aria-expanded={showNumbers}
          >
            {showNumbers ? "Hide the numbers" : "Show the numbers"}
          </button>
        )}
      </div>
      {showNumbers && (
        <dl className="mt-3 divide-y divide-border border-t border-border text-sm tabular-nums">
          {facts.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-4 py-1.5">
              <dt className="text-ink-3">{label}</dt>
              <dd className="text-right text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function ChatAssistant({ month }: { month: string }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open || suggestions.length) return;
    fetchChatSuggestions()
      .then((data) => setSuggestions(data.suggestions))
      .catch(() => setSuggestions([]));
  }, [open, suggestions.length]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;

    // The last answer's plan lets "and in July?" continue the same topic.
    const lastReply = [...messages].reverse().find((m) => m.role === "assistant");
    const previous = lastReply?.role === "assistant" ? lastReply.reply.plan : null;

    setMessages((current) => [...current, { role: "user", text }]);
    setInput("");
    setBusy(true);
    try {
      const reply = await askQuestion(text, month, previous);
      setMessages((current) => [...current, { role: "assistant", reply }]);
    } catch {
      setMessages((current) => [...current, { role: "error", text: "Sorry, I couldn't answer that right now." }]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    ask(input);
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed right-4 bottom-4 z-30 flex items-center gap-2 rounded-full bg-brand px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-brand-dark sm:right-6 sm:bottom-6"
        >
          <span className="flex h-6 w-6 items-center justify-center rounded-sm bg-white text-[11px] font-bold text-brand">
            AI
          </span>
          Ask about my money
        </button>
      )}

      {open && (
        <aside
          className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-border bg-background shadow-2xl sm:w-[420px]"
          aria-label="Ask about my money"
        >
          <header className="flex items-center justify-between bg-brand px-5 py-4 text-white">
            <div>
              <p className="font-semibold">Ask about my money</p>
              <p className="text-xs text-white/70">
                Answers use your {formatMonth(month)} data. Numbers are calculated, never guessed.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded-sm px-2 py-1 text-xl leading-none text-white/80 hover:bg-white/10 hover:text-white"
              aria-label="Close"
            >
              ×
            </button>
          </header>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
            {messages.length === 0 && (
              <div className="rounded border border-border bg-surface p-4 text-sm text-ink-2">
                Ask anything about your spending and income, for example how much you spent on groceries or
                where most of your money went. I can&apos;t give investment or credit advice.
              </div>
            )}

            {messages.map((message, index) =>
              message.role === "user" ? (
                <div key={index} className="flex justify-end">
                  <p className="max-w-[85%] rounded bg-brand px-3 py-2 text-[15px] text-white">{message.text}</p>
                </div>
              ) : message.role === "assistant" ? (
                <AssistantMessage key={index} reply={message.reply} />
              ) : (
                <p key={index} className="rounded border border-warning/40 bg-warning-bg p-3 text-sm text-warning">
                  {message.text}
                </p>
              ),
            )}

            {busy && (
              <div className="rounded border border-border bg-surface p-3 text-sm text-ink-3">
                <span className="animate-pulse">Calculating and checking your answer…</span>
              </div>
            )}
          </div>

          {suggestions.length > 0 && messages.length < 2 && (
            <div className="flex flex-wrap gap-2 border-t border-border px-4 py-3">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => ask(suggestion)}
                  disabled={busy}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-ink-2 hover:border-brand hover:text-brand disabled:opacity-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          <form onSubmit={onSubmit} className="flex gap-2 border-t border-border bg-surface p-3">
            <input
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              maxLength={500}
              placeholder="e.g. How much did I spend on transport?"
              className="min-w-0 flex-1 rounded border border-border bg-surface px-3 py-2 text-[15px] text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none"
              aria-label="Your question"
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="rounded bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50"
            >
              Ask
            </button>
          </form>
        </aside>
      )}
    </>
  );
}
