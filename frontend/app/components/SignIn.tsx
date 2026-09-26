"use client";

import { useEffect, useState } from "react";

import { type DemoCustomer, type Session, type Tenant, demoSignIn, fetchDemoCustomers } from "../lib/api";

const DESCRIPTIONS: Record<string, string> = {
  "demo-customer": "Sample account from the pitch: restaurant spending jumps in August.",
  "demo-young-professional": "12 months in Berlin: rent, eating out, weekend habits.",
  "demo-family": "Family of four in Munich: groceries, childcare, a car.",
  "demo-student": "Student in Hamburg: tight budget, part-time income.",
};

export function SignIn({
  tenant,
  notice,
  onSignedIn,
}: {
  tenant: Tenant;
  notice: string | null;
  onSignedIn: (session: Session) => void;
}) {
  const [customers, setCustomers] = useState<DemoCustomer[] | null | undefined>(undefined);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDemoCustomers()
      .then(setCustomers)
      .catch(() => setError("The sign-in service didn't respond. Please try again."));
  }, []);

  async function signIn(ref: string) {
    setBusy(ref);
    setError(null);
    try {
      onSignedIn(await demoSignIn(ref));
    } catch {
      setError("Sign-in failed. Please try again.");
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto mt-6 max-w-xl">
      <div className="rounded border border-border bg-surface p-6 sm:p-8">
        <h1 className="text-xl font-semibold text-ink">Sign in to {tenant.bank_name}</h1>

        {notice && (
          <p role="status" className="mt-3 rounded-sm bg-warning-bg px-3 py-2 text-sm text-warning">
            {notice}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-3 rounded-sm bg-critical-bg px-3 py-2 text-sm text-critical">
            {error}
          </p>
        )}

        {customers === undefined && !error && <p className="mt-4 text-sm text-ink-3">Loading…</p>}

        {customers === null && (
          <p className="mt-4 text-sm leading-6 text-ink-2">
            Customers sign in through {tenant.bank_name}&apos;s own app, which opens this page with a secure
            session. {tenant.assistant_name} never sees your password.
          </p>
        )}

        {customers && (
          <>
            <p className="mt-2 text-sm leading-6 text-ink-2">
              <strong className="font-semibold text-ink">Demo sign-in.</strong> Choose a demo customer. In a live
              bank, customers arrive already signed in from the bank&apos;s app; {tenant.assistant_name} never
              sees passwords.
            </p>
            <ul className="mt-5 space-y-3">
              {customers.map((customer) => (
                <li key={customer.ref}>
                  <button
                    type="button"
                    onClick={() => signIn(customer.ref)}
                    disabled={busy !== null}
                    className="w-full rounded border border-border px-4 py-3 text-left hover:border-brand hover:bg-brand-soft disabled:opacity-60"
                  >
                    <span className="block font-medium text-ink">
                      {customer.name}
                      {busy === customer.ref && <span className="ml-2 text-sm text-ink-3">Signing in…</span>}
                    </span>
                    {DESCRIPTIONS[customer.ref] && (
                      <span className="mt-0.5 block text-sm text-ink-3">{DESCRIPTIONS[customer.ref]}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
