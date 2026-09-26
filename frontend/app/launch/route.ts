import { type NextRequest, NextResponse } from "next/server";

import { API_URL, clearSession, webAppSecretHeader, writeSession } from "../lib/server/session";

/**
 * The bank app opens /launch?code=… after signing its customer in. The code is exchanged server-side
 * (with the web app's client secret) for a session, stored in an httpOnly cookie, and the customer is
 * redirected to "/", which also removes the code from the address bar and browser history.
 */
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code") ?? "";
  const home = new URL("/", request.nextUrl.origin);

  if (code.length < 20 || code.length > 100) {
    home.searchParams.set("launch", "invalid");
    return NextResponse.redirect(home, 303);
  }

  const response = await fetch(`${API_URL}/api/launch-codes/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...webAppSecretHeader() },
    body: JSON.stringify({ code }),
    cache: "no-store",
  });

  if (!response.ok) {
    await clearSession();
    home.searchParams.set("launch", "expired");
    return NextResponse.redirect(home, 303);
  }

  const session = await response.json();
  await writeSession({
    token: session.token,
    tenant: session.tenant,
    customerName: session.customer.name,
    expiresAt: session.expires_at,
  });
  return NextResponse.redirect(home, 303);
}
