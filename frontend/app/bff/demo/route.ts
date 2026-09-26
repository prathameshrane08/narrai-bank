import { type NextRequest, NextResponse } from "next/server";

import { API_URL, checkWriteRequest, writeSession } from "../../lib/server/session";

/**
 * Demo sign-in (pitches only). The API refuses unless NARRAI_DEMO_MODE=1 and the customer is a seeded
 * demo customer; the session then lives in the same httpOnly cookie as a real launch.
 */
export async function POST(request: NextRequest) {
  const refused = checkWriteRequest(request);
  if (refused) return NextResponse.json({ detail: refused }, { status: 403 });

  const { tenant, customer_ref } = (await request.json().catch(() => ({}))) as {
    tenant?: string;
    customer_ref?: string;
  };
  if (!tenant || !/^[a-z0-9-]{2,40}$/.test(tenant) || !customer_ref) {
    return NextResponse.json({ detail: "Invalid request." }, { status: 422 });
  }

  const response = await fetch(`${API_URL}/api/demo/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-NarrAI-Tenant": tenant },
    body: JSON.stringify({ customer_ref }),
    cache: "no-store",
  });
  if (!response.ok) {
    return NextResponse.json(await response.json().catch(() => ({ detail: "Sign-in failed." })), {
      status: response.status,
    });
  }

  const session = await response.json();
  const stored = { token: session.token, tenant, customerName: session.customer.name, expiresAt: session.expires_at };
  await writeSession(stored);
  return NextResponse.json({ signedIn: true, tenant, customerName: stored.customerName, expiresAt: stored.expiresAt });
}
