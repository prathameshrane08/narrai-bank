import { type NextRequest, NextResponse } from "next/server";

import { API_URL, checkWriteRequest, clearSession, readSession } from "../../lib/server/session";

/** Who is signed in, for the page. Never returns the token itself. */
export async function GET() {
  const session = await readSession();
  const body = session
    ? { signedIn: true, tenant: session.tenant, customerName: session.customerName, expiresAt: session.expiresAt }
    : { signedIn: false };
  return NextResponse.json(body, { headers: { "Cache-Control": "no-store" } });
}

/** Sign out: revoke the session at the API (so the token is dead everywhere), then drop the cookie. */
export async function DELETE(request: NextRequest) {
  const refused = checkWriteRequest(request);
  if (refused) return NextResponse.json({ detail: refused }, { status: 403 });

  const session = await readSession();
  if (session) {
    await fetch(`${API_URL}/api/sessions/current/revoke`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
    }).catch(() => undefined); // the cookie is cleared regardless; the token also expires on its own
  }
  await clearSession();
  return new NextResponse(null, { status: 204 });
}
