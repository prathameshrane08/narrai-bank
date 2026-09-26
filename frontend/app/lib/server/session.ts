import "server-only";

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

/**
 * The customer's NarrAI session lives in an httpOnly cookie on the web app's own domain, so page
 * scripts (and anything injected into them) can never read the token. The web app's server attaches
 * it to API calls (see app/bff). Stateless, so it runs unchanged on Vercel functions.
 */

// Server-side address of the NarrAI API (can differ from the browser-facing one, e.g. a private URL).
export const API_URL = process.env.NARRAI_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const SECURE = process.env.NODE_ENV === "production";
// "__Host-" makes the browser refuse the cookie unless it is Secure, host-only and path=/.
const COOKIE = SECURE ? "__Host-narrai_session" : "narrai_session";

export type StoredSession = { token: string; tenant: string; customerName: string; expiresAt: string };

export async function readSession(): Promise<StoredSession | null> {
  const raw = (await cookies()).get(COOKIE)?.value;
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as StoredSession;
    return new Date(session.expiresAt) > new Date() ? session : null;
  } catch {
    return null;
  }
}

export async function writeSession(session: StoredSession) {
  const maxAge = Math.max(0, Math.floor((new Date(session.expiresAt).getTime() - Date.now()) / 1000));
  (await cookies()).set(COOKIE, JSON.stringify(session), {
    httpOnly: true,
    secure: SECURE,
    // Lax, not Strict: the bank app opens /launch from another site, and the first page after the
    // redirect must see the cookie. State-changing calls are protected by checkWriteRequest below.
    sameSite: "lax",
    path: "/",
    maxAge,
  });
}

export async function clearSession() {
  (await cookies()).delete(COOKIE);
}

/**
 * Cross-site request forgery protection for anything that changes data: the request must carry our
 * custom header (browsers only send it from our own pages) and, when present, a same-origin Origin.
 */
export function checkWriteRequest(request: NextRequest): string | null {
  if (request.headers.get("x-narrai-csrf") !== "1") return "Missing request protection header.";
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) return "Cross-site request refused.";
  return null;
}

export function webAppSecretHeader(): Record<string, string> {
  const secret = process.env.NARRAI_WEBAPP_SECRET;
  if (!secret) throw new Error("NARRAI_WEBAPP_SECRET is not set for the web app server");
  return { "X-NarrAI-Client-Secret": secret };
}
