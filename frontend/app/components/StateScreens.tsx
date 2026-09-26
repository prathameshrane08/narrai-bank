function Bone({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-sm bg-ink-3/15 ${className}`} />;
}

/** Placeholder with the page's real shape, so nothing jumps when data arrives. */
export function LoadingSkeleton() {
  return (
    <div aria-busy="true" aria-live="polite">
      <p className="sr-only">Loading your finances…</p>
      <Bone className="h-4 w-32" />
      <Bone className="mt-2 h-7 w-48" />
      <div className="mt-5 space-y-5">
        <div className="h-44 animate-pulse rounded bg-ink-3/20" />
        <div className="rounded border border-border bg-surface p-6">
          <Bone className="h-5 w-64" />
          <div className="mt-6 grid gap-6 md:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="space-y-2">
                <Bone className="h-4 w-40" />
                <Bone className="h-3 w-full" />
                <Bone className="h-3 w-2/3" />
              </div>
            ))}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="rounded border border-border bg-surface p-5">
              <Bone className="h-3 w-24" />
              <Bone className="mt-3 h-7 w-32" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="mx-auto mt-10 max-w-lg rounded border border-border bg-surface p-8 text-center">
      <p className="text-3xl" aria-hidden>
        ⚠
      </p>
      <h1 className="mt-3 text-lg font-semibold text-ink">We can&apos;t show your finances right now</h1>
      <p className="mt-2 text-sm leading-6 text-ink-2">{message}</p>
      <p className="mt-1 text-sm text-ink-3">Your money is safe; this only affects what this page can display.</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-6 rounded-sm bg-brand px-5 py-2.5 text-sm font-semibold text-on-brand hover:bg-brand-dark"
      >
        Try again
      </button>
    </div>
  );
}
